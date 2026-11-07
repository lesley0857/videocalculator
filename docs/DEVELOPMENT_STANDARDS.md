# Development Standards

**Project:** Commercial Online Calculator Platform  
**Last updated:** 2026-11-07  

---

## Table of Contents

1. [Service-layer conventions](#1-service-layer-conventions)  
2. [Data conventions](#2-data-conventions)  
3. [Model conventions](#3-model-conventions)  
4. [View conventions](#4-view-conventions)  
5. [Testing conventions](#5-testing-conventions)  
6. [Migration conventions](#6-migration-conventions)  
7. [Code style and naming](#7-code-style-and-naming)  

---

## 1. Service-layer conventions

### 1.1 Why services, not fat models or fat views

Business logic does not belong in Django views (they handle HTTP only) or in model
methods (they own persistence only). All meaningful business operations live in
`services.py` modules inside the relevant application.

**Correct**
```python
# apps/orders/views.py
from apps.orders.services import create_order

def checkout_view(request):
    order = create_order(user=request.user, total_amount=amount, currency='USD')
    ...
```

**Wrong**
```python
# apps/orders/views.py
from apps.orders.models import Order

def checkout_view(request):
    order = Order.objects.create(user=request.user, total_amount=amount)
    ...  # business logic leaking into the view
```

---

### 1.2 Service function signatures

Every service function must follow these conventions:

1. **Plain Python inputs.** Accept primitive types (`str`, `int`, `Decimal`,
   `datetime`) or model instances. Never accept raw request objects — views extract
   values from the request and pass them in.

2. **Return typed values.** Return a model instance, a dataclass, or a plain dict.
   Never return a Django `QuerySet` from a service unless the caller is expected to
   iterate it immediately.

3. **Full type annotations.** All public service functions must include parameter
   types and a return type.

```python
# Correct — typed, plain inputs
def create_order(user: User, total_amount: Decimal, currency: str = 'USD') -> Order:
    ...

# Wrong — accepting a request object
def create_order(request) -> Order:
    ...
```

---

### 1.3 Validation and error handling

Services are responsible for validating domain rules. HTTP-layer validation
(form/serializer) happens in views before the service is called.

**Raise standard Python exceptions for domain rule violations:**

```python
# Domain validation — raise ValueError or a custom exception
def create_order(user: User, total_amount: Decimal, currency: str = 'USD') -> Order:
    if total_amount <= Decimal('0'):
        raise ValueError("Order amount must be greater than zero.")
    ...
```

**Do not catch and silently swallow exceptions inside services.** Let them
propagate to the view, which translates them into the appropriate HTTP response.

**Custom exception classes** should be defined in the application's module
(e.g., `apps/orders/exceptions.py`) when a named exception aids clarity. Do not
create custom exception classes unless a caller genuinely needs to distinguish that
exception type from others.

---

### 1.4 Database transactions

Wrap multi-step write operations in `transaction.atomic()`:

```python
from django.db import transaction

def record_payment_success(payment: Payment, reference_id: str) -> Payment:
    with transaction.atomic():
        payment.status = PaymentStatus.SUCCESSFUL
        payment.reference_id = reference_id
        payment.save(update_fields=['status', 'reference_id', 'updated_at'])
        mark_order_as_paid(payment.order)
        grant_entitlement(user=payment.order.user, product=payment.order.product)
    return payment
```

**Rules:**
- Use `transaction.atomic()` whenever a service writes to more than one model.
- Use `save(update_fields=[...])` on every model save that touches only specific
  fields. This avoids unintentional overwrites and reduces lock scope.
- Never place network calls (payment gateway, email dispatch) inside a
  `transaction.atomic()` block. Network operations cannot be rolled back.

---

### 1.5 Separation of domain logic from external integrations

Internal services and external adapters must remain separate:

| Layer | Location | Responsibility |
|---|---|---|
| Domain service | `apps/<name>/services.py` | Business decisions |
| Gateway adapter | `apps/payments/gateways/<provider>.py` | HTTP calls to external APIs |
| Notification service | `apps/notifications/services.py` | Formatting and dispatch |

A domain service calls a gateway adapter to get raw data, then makes the business
decision itself. Gateway adapters return plain Python dicts — they never update
models or trigger further business logic.

```python
# Correct — gateway returns a dict, service makes the decision
raw = gateway.handle_webhook(payload, signature)
if raw.get('event') == 'payment.succeeded':
    record_payment_success(payment, reference_id=raw['transaction_id'])

# Wrong — gateway calling a service
class StripeGateway:
    def handle_webhook(self, ...):
        record_payment_success(...)  # gateway must not do this
```

---

## 2. Data conventions

### 2.1 Monetary values

- **Always use `decimal.Decimal`** for monetary amounts in Python code.
- **Always use `DecimalField(max_digits=10, decimal_places=2)`** in Django models.
- **Never use `float`** for money. Floating-point arithmetic introduces rounding
  errors that are unacceptable in financial calculations.

```python
from decimal import Decimal

price = Decimal('29.99')      # correct
price = 29.99                 # wrong — float
```

When reading a value from an external API (which may return a string or int), convert
it immediately:

```python
amount = Decimal(str(api_response['amount_in_cents'])) / Decimal('100')
```

---

### 2.2 Currency representation

- Currency is stored as a three-letter ISO 4217 code (`CharField(max_length=3)`).
- Default currency is `'USD'`.
- Currency formatting for display is a UI concern and is never stored in the database.
- Never store currency symbols (`$`, `€`) in the database.

---

### 2.3 Timestamps

- All timestamps in models use timezone-aware `DateTimeField`.
- The global `TIME_ZONE` setting is `'UTC'`. All stored timestamps are UTC.
- Always use `django.utils.timezone.now()` instead of `datetime.datetime.now()`.

```python
from django.utils import timezone

record.last_active = timezone.now()   # correct
record.last_active = datetime.now()   # wrong — naive datetime
```

---

### 2.4 JSON fields

`JSONField` is used in several models (`CalculationRecord.inputs`,
`CalculationRecord.results`, `Payment.metadata`, `AnalyticsEvent.properties`).

Rules:
- Always default to `default=dict` for object-shaped fields.
- Always default to `default=list` for array-shaped fields.
- Never store Python objects that are not JSON-serialisable (e.g., `Decimal`,
  `datetime`). Convert to `str` before storing.
- Treat JSON fields as **append-only snapshots** in `CalculationRecord`. Once a
  record is written it must not be mutated, so that historical data is preserved.

---

### 2.5 Historical records and snapshots

`CalculationRecord` captures a point-in-time snapshot of what the user entered and
what the engine returned. This is intentional:

- If calculator logic changes in the future, old records still reflect what was
  calculated at the time.
- Do not store normalised foreign keys into inputs or results — store the raw values
  as they were at the time of calculation.
- Do not add an `updated_at` field to `CalculationRecord`. It is immutable after
  creation.

---

## 3. Model conventions

### 3.1 Primary keys

All custom models use `UUIDField` as the primary key:

```python
import uuid
from django.db import models

id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
```

This prevents enumeration attacks and aligns with external payment references.
Junction models (through tables with no independent identity) may use the default
auto-incrementing integer PK.

---

### 3.2 Standard timestamp fields

Every model that is not an immutable record should include:

```python
created_at = models.DateTimeField(auto_now_add=True)
updated_at = models.DateTimeField(auto_now=True)
```

Immutable records (e.g., `CalculationRecord`, `AnalyticsEvent`) include only
`created_at`.

---

### 3.3 Referencing the user model

Always reference the user via settings:

```python
from django.conf import settings

user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, ...)
```

In service or utility code where you need the actual class:

```python
from django.contrib.auth import get_user_model
User = get_user_model()
```

---

### 3.4 `on_delete` policy

| Relationship | Recommended `on_delete` | Rationale |
|---|---|---|
| Order → User | `CASCADE` | An order without a user is orphaned data |
| Payment → Order | `CASCADE` | Payment without order has no context |
| Entitlement → User | `CASCADE` | Access without user is meaningless |
| Entitlement → Product | `CASCADE` | Entitlement for a deleted product is invalid |
| AnalyticsEvent → User | `SET_NULL` | Historical events should survive user deletion |
| CalculationRecord → User | `CASCADE` | Acceptable; reconsider if audit log is required |

---

### 3.5 Soft deletes

No soft-delete framework is introduced at this stage. Use `is_active = False`
booleans on specific models where deactivation rather than deletion is the
appropriate lifecycle action (e.g., `Product.is_active`, `Entitlement.is_active`,
`User.is_active`).

---

## 4. View conventions

Views handle the HTTP contract only. They must:

1. Parse and validate the incoming request (form, query parameters, JSON body).
2. Call one or more services with plain Python values.
3. Render and return the HTTP response.

Views must not:
- Query the database directly.
- Contain business logic or conditional state-transition code.
- Import from `apps.payments.gateways` or any external SDK.

```python
# Correct view — thin, delegates to service
class CheckoutView(View):
    def post(self, request):
        form = CheckoutForm(request.POST)
        if not form.is_valid():
            return render(request, 'checkout.html', {'form': form})
        order = create_order(
            user=request.user,
            total_amount=form.cleaned_data['amount'],
        )
        return redirect('orders:confirmation', pk=order.pk)
```

---

## 5. Testing conventions

### 5.1 Mandatory coverage rule

> **Every new business-critical service function must have at least one automated
> test before the corresponding feature is merged.**

Business-critical is defined as: any service that creates, modifies, or validates
data related to orders, payments, entitlements, or calculation records.

---

### 5.2 Test organisation

```
apps/<name>/tests/
    __init__.py
    test_models.py      ← field constraints, __str__, is_valid() etc.
    test_services.py    ← service function behaviour
    test_views.py       ← HTTP status codes and response content
```

For calculator engines:

```
apps/calculators/engines/tests/
    __init__.py
    test_<engine_name>.py   ← plain unittest.TestCase, no Django required
```

---

### 5.3 Which test base class to use

| What you are testing | Base class |
|---|---|
| Settings and URL resolution | `SimpleTestCase` |
| Models and services (database) | `TestCase` |
| Views (with Django test client) | `TestCase` |
| Calculation engines (pure logic) | `unittest.TestCase` |
| Payment gateway adapters (mocked) | `TestCase` with `unittest.mock.patch` |

---

### 5.4 Model tests

Test field constraints, `__str__` output, and any model methods (`is_valid()` etc.).
Do not test Django ORM internals.

```python
class EntitlementIsValidTests(TestCase):
    def test_active_entitlement_with_no_expiry_is_valid(self):
        entitlement = EntitlementFactory(is_active=True, expires_at=None)
        self.assertTrue(entitlement.is_valid())

    def test_expired_entitlement_is_invalid(self):
        past = timezone.now() - timedelta(days=1)
        entitlement = EntitlementFactory(is_active=True, expires_at=past)
        self.assertFalse(entitlement.is_valid())
```

---

### 5.5 Service tests

Test inputs, outputs, and state changes. Use the database. Do not mock the ORM.

```python
class GrantEntitlementTests(TestCase):
    def test_grant_creates_entitlement_for_user_and_product(self):
        user = UserFactory()
        product = ProductFactory(slug='talking-flyer-calculator')
        entitlement = grant_entitlement(user=user, product=product)
        self.assertTrue(entitlement.is_active)
        self.assertIsNone(entitlement.expires_at)

    def test_grant_reactivates_inactive_entitlement(self):
        user = UserFactory()
        product = ProductFactory(slug='talking-flyer-calculator')
        existing = EntitlementFactory(user=user, product=product, is_active=False)
        updated = grant_entitlement(user=user, product=product)
        self.assertEqual(existing.pk, updated.pk)
        self.assertTrue(updated.is_active)
```

---

### 5.6 View tests

Test HTTP status codes and response content. Do not test business logic through
views — that is covered by service tests.

```python
class ProductListViewTests(TestCase):
    def test_returns_200_for_anonymous_users(self):
        response = self.client.get(reverse('products:list'))
        self.assertEqual(response.status_code, 200)
```

---

### 5.7 Calculation engine tests

Engines are plain Python and require no Django test infrastructure:

```python
import unittest
from apps.calculators.engines.talking_flyer import TalkingFlyerEngine

class TalkingFlyerEngineTests(unittest.TestCase):
    def test_basic_calculation_returns_expected_keys(self):
        engine = TalkingFlyerEngine()
        result = engine.calculate({'quantity': 1000, 'unit_price': '0.25'})
        self.assertIn('total_cost', result)
        self.assertIn('unit_cost', result)
```

---

### 5.8 Payment gateway tests

Always mock external network calls. Never call a live payment API in automated tests.

```python
from unittest.mock import patch, MagicMock

class StripeGatewayTests(TestCase):
    @patch('apps.payments.gateways.stripe_gateway.stripe.checkout.Session.create')
    def test_create_checkout_session_returns_url(self, mock_create):
        mock_create.return_value = MagicMock(url='https://checkout.stripe.com/xxx')
        gateway = StripeGateway()
        result = gateway.create_checkout_session('order-id', '29.99', 'USD')
        self.assertIn('checkout_url', result)
```

---

### 5.9 Entitlement access tests

Test the public API, not the internals of the `Entitlement` model:

```python
class UserHasProductAccessTests(TestCase):
    def test_returns_true_when_user_has_active_entitlement(self):
        user = UserFactory()
        product = ProductFactory(slug='talking-flyer-calculator')
        EntitlementFactory(user=user, product=product, is_active=True)
        self.assertTrue(user_has_product_access(user, 'talking-flyer-calculator'))

    def test_returns_false_for_different_product(self):
        user = UserFactory()
        ProductFactory(slug='talking-flyer-calculator')
        # User has NOT been granted an entitlement
        self.assertFalse(user_has_product_access(user, 'talking-flyer-calculator'))
```

---

## 6. Migration conventions

- Run `python manage.py makemigrations <app>` for each application individually
  when changing its models. This keeps migrations scoped and reviewable.
- Commit migrations alongside the model change in the same commit.
- Never edit a migration that has already been applied in any shared environment
  (development, staging, production). Create a new migration instead.
- Squash migrations only on a dedicated branch, with approval, and only before
  the first production release.
- When adding a new non-nullable field to an existing model, always provide a
  `default` or use `null=True` with a follow-up migration.

---

## 7. Code style and naming

### Naming conventions

| Item | Convention | Example |
|---|---|---|
| Python files | `snake_case` | `payment_service.py` |
| Classes | `PascalCase` | `PaymentGateway` |
| Functions / methods | `snake_case` | `grant_entitlement()` |
| Constants / choices | `UPPER_SNAKE` | `PaymentStatus.SUCCESSFUL` |
| URL names | `snake_case` | `payments:webhook` |
| Template names | `snake_case` | `checkout_success.html` |
| DB columns | `snake_case` (auto) | `created_at` |
| Environment variables | `UPPER_SNAKE` | `DB_PASSWORD` |
| Product slugs | `kebab-case` | `talking-flyer-calculator` |

### Import order

Follow the standard Python import order enforced by `isort`:

1. Standard library
2. Third-party packages (Django, etc.)
3. Local application imports (`from apps.<name>...`)

Relative imports (`.models`, `.services`) are permitted within the same application
package. Cross-application imports must always use the absolute path
(`from apps.products.models import Product`).

