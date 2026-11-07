# System Architecture

**Project:** Commercial Online Calculator Platform  
**Architecture style:** Modular Django monolith  
**Last updated:** 2026-11-07  

---

## Table of Contents

1. [Structural overview](#1-structural-overview)  
2. [Application responsibilities and boundaries](#2-application-responsibilities-and-boundaries)  
3. [Dependency rules](#3-dependency-rules)  
4. [Data flow for a typical purchase](#4-data-flow-for-a-typical-purchase)  
5. [Data flow for a calculator session](#5-data-flow-for-a-calculator-session)  

---

## 1. Structural overview

```
video_calculator/
├── apps/                   ← all domain applications live here
│   ├── accounts/
│   ├── products/
│   ├── orders/
│   ├── payments/
│   │   └── gateways/       ← external provider adapters only
│   ├── entitlements/
│   ├── devices/
│   ├── calculators/
│   │   └── engines/        ← pure calculation logic only
│   ├── notifications/
│   └── analytics/
├── videocalculatorproject/ ← project configuration (settings, URLs, wsgi/asgi)
├── templates/              ← project-wide HTML templates
├── static/                 ← project-wide CSS, JS, images
└── media/                  ← user-uploaded files at runtime
```

The `apps/` directory is added to `sys.path` so each application can be referenced
as `apps.<name>` in `INSTALLED_APPS` and imported as `from apps.<name>.models import ...`.

---

## 2. Application responsibilities and boundaries

Each application owns a **single coherent domain**. The boundary rules below define
what belongs inside an application and what must be delegated elsewhere.

---

### 2.1 `accounts` — user identity

**Owns:**
- The custom `User` model (email as `USERNAME_FIELD`, UUID primary key).
- The `UserManager` with `create_user` / `create_superuser`.
- Account lifecycle services: registration, deactivation.
- Authentication-related views (login, logout, password reset) when implemented.

**Does not own:**
- Product access decisions → delegate to `entitlements`.
- Order history → belongs to `orders`.
- Device recognition → belongs to `devices`.
- Notification dispatch → belongs to `notifications`.

**Key rule:** Any other application that needs to reference the authenticated user
must use `settings.AUTH_USER_MODEL` in model `ForeignKey` declarations and
`get_user_model()` in service-layer code, never importing `User` directly from
`apps.accounts.models`.

---

### 2.2 `products` — product catalogue

**Owns:**
- `Product` model: `name`, `slug`, `description`, `is_active`.
- Catalogue query services: `get_active_products()`, `get_product_by_slug()`.

**Does not own:**
- Pricing rules → will live in `products` or a future `pricing` module when needed.
- Access decisions → belongs to `entitlements`.
- Order creation → belongs to `orders`.
- Calculator logic → belongs to `calculators`.

**Key rule:** `products.slug` is the **canonical identifier** used by other
applications when referencing a product by name (e.g., `'talking-flyer-calculator'`,
`'ai-video-calculator'`). Do not hard-code product IDs in other applications.

---

### 2.3 `orders` — commercial transactions

**Owns:**
- `Order` model and `OrderStatus` choices
  (`PENDING` → `PAID` → `CANCELLED` or `REFUNDED`).
- Order creation and state-transition services.
- The `mark_order_as_paid()` service, which is the **only authorised entry-point**
  for transitioning an order to `PAID` status.

**Does not own:**
- Payment provider communication → belongs to `payments`.
- Entitlement grants → belongs to `entitlements`.
  When an order is paid, the payment service calls `entitlements` to grant access.

**Key rule:** `orders` does not import from `payments` or `entitlements`.
Those applications call into `orders`, not the reverse. This keeps the dependency
graph acyclic.

---

### 2.4 `payments` — financial records and provider integration

**Owns:**
- `Payment` model: `order`, `provider`, `reference_id`, `amount`, `currency`,
  `status`, `metadata`.
- `PaymentStatus` choices: `INITIATED`, `SUCCESSFUL`, `FAILED`, `REFUNDED`.
- Domain payment services: `initiate_payment()`, `record_payment_success()`,
  `record_payment_failure()`.
- The `gateways/` sub-package, which contains **only** thin adapter classes that
  communicate with external payment providers.

**Does not own:**
- Order state management (calls `orders.services.mark_order_as_paid()`).
- Entitlement granting (calls `entitlements.services.grant_entitlement()`).
- Any provider SDK or secret key — those live in environment variables only.

**Gateway sub-package rule:** `gateways/` classes must implement
`BasePaymentGateway` and must **not** contain domain business logic. They
translate external provider responses into plain Python dicts. Business decisions
(success, failure, refund) happen in `payments.services`, not in gateway adapters.

---

### 2.5 `entitlements` — product access control

**Owns:**
- `Entitlement` model: `user`, `product`, `is_active`, `expires_at`.
- `Entitlement.is_valid()` method: the single authoritative check for whether an
  entitlement is currently active and unexpired.
- `grant_entitlement()` service: creates or reactivates an entitlement record.
- `user_has_product_access(user, product_slug)` service: the **public access-check
  API** that all other applications must call. It is the only way a non-entitlements
  application should ask "can this user use this product?".

**Does not own:**
- Payment logic — entitlements are granted as a consequence of payment, not managed
  by the payment application directly. The payment service calls `grant_entitlement`
  after confirming success.
- Product definition — imports `Product` from `apps.products.models`.

**Key rule:** Every access-control check in a view, service, or decorator must
route through `entitlements.services.user_has_product_access()`. Nothing should
query the `Entitlement` table directly from outside the `entitlements` application.

---

### 2.6 `devices` — device fingerprinting and session security

**Owns:**
- `Device` model: `user`, `device_fingerprint`, `user_agent`, `ip_address`,
  `last_active`, `is_trusted`.
- `register_or_update_device()` service.
- `revoke_device()` service.

**Does not own:**
- Authentication sessions (Django's session framework handles those).
- Entitlement or access decisions.

**Key rule:** Devices are informational and security-supportive. No other
application's core business logic should depend on a user having a registered
device.

---

### 2.7 `calculators` — calculation records and engine interface

**Owns:**
- `CalculationRecord` model: `user`, `product`, `inputs` (JSONField),
  `results` (JSONField), `created_at`.
- `save_calculation_record()` service: persists a completed calculation.
- The `services/` sub-package:
  - `narration.py`: text normalisation, word counting, WPM validation, duration calculation.
  - `clip_planning.py`: provider-independent clip capacity calculation, DP sequence optimisation, plan metrics.
  - `narration_segmentation.py`: sequential text segmentation, sentence-boundary awareness, integrity validation.
- The `engines/` sub-package, which contains the `BaseCalculationEngine` abstract
  class and concrete engine implementations (`NarrationEngine`, `UniversalClipPlanningEngine`).

**Does not own:**
- UI rendering or HTTP request handling (those belong in views).
- Entitlement checks before running calculations (views or a decorator call
  `entitlements.services.user_has_product_access()` before invoking an engine).
- Pricing or payment logic.
- AI provider integrations or model-specific video rendering (deferred to future tasks).

**Engine sub-package rule:** Engines receive a validated Python dict and return
a Python dict. They must not import from Django models, views, or any application
outside `calculators.engines` and calculator domain services. This keeps them
independently testable with plain `unittest` / `SimpleTestCase`.

---

### 2.8 `notifications` — transactional alerts

**Owns:**
- `Notification` model: `user`, `notification_type`, `subject`, `body`, `is_read`,
  `sent_at`.
- `send_email_notification()` service.
- Future services for in-app notifications.

**Does not own:**
- The trigger for sending a notification (other services call notification services;
  `notifications` does not listen for signals automatically in this phase).
- Email configuration (that belongs to Django settings).

**Key rule:** Any application that needs to send a message to a user imports
`from apps.notifications.services import send_email_notification` and calls it
directly. Do not place notification dispatch logic inside order, payment, or
entitlement service code — call the notifications service and return.

---

### 2.9 `analytics` — event tracking

**Owns:**
- `AnalyticsEvent` model: `user` (nullable), `event_name`, `properties` (JSONField),
  `created_at`.
- `track_event()` service.

**Does not own:**
- Business decisions based on event data — analytics is append-only and
  observational.
- Reporting dashboards (future concern).

**Key rule:** Calls to `analytics.services.track_event()` are always fire-and-forget
additions to a service function. They must never block a business-critical code path
or raise exceptions that propagate to the caller.

---

## 3. Dependency rules

The table below summarises which applications are permitted to import from which.
An arrow (→) means "may import from".

```
accounts    → (nothing except Django built-ins and stdlib)
products    → (nothing except Django built-ins and stdlib)
orders      → accounts (via settings.AUTH_USER_MODEL), products
payments    → orders, accounts (via settings.AUTH_USER_MODEL)
entitlements → accounts (via settings.AUTH_USER_MODEL), products
devices     → accounts (via settings.AUTH_USER_MODEL)
calculators → accounts (via settings.AUTH_USER_MODEL), products
notifications → accounts (via settings.AUTH_USER_MODEL)
analytics   → accounts (via settings.AUTH_USER_MODEL)
```

**Forbidden imports:**
- `orders` must not import from `payments` or `entitlements`.
- `products` must not import from any other local application.
- `accounts` must not import from any other local application.
- Any engine inside `calculators.engines` must not import from Django models.

---

## 4. Data flow for a typical purchase

```
Browser
  │
  ▼
orders.views / orders.services.create_order()
  │   Creates Order (status=PENDING)
  ▼
payments.services.initiate_payment()
  │   Creates Payment (status=INITIATED)
  │
  ├──► payments.gateways.<Provider>.create_checkout_session()
  │       Returns provider checkout URL
  │
  ◄── Browser completes checkout on provider side ──►
  │
payments.views (webhook handler)
  │
  ├──► payments.gateways.<Provider>.handle_webhook()
  │       Parses and validates provider event
  │
  ├──► payments.services.record_payment_success()
  │       Payment status → SUCCESSFUL
  │       Calls orders.services.mark_order_as_paid()
  │           Order status → PAID
  │       Calls entitlements.services.grant_entitlement()
  │           Entitlement created/activated
  │       Calls notifications.services.send_email_notification()
  │           Confirmation email dispatched
  │       Calls analytics.services.track_event('order.paid')
  │
  ◄── User can now access the purchased product ──►
```

---

## 5. Data flow for a calculator session

```
Browser
  │
  ▼
calculators.views
  │   Calls entitlements.services.user_has_product_access(user, product_slug)
  │   Returns 403 if False
  │
  ▼
calculators.engines.<ConcreteEngine>.calculate(validated_inputs)
  │   Pure computation — no Django dependencies
  │   Returns structured results dict
  │
  ▼
calculators.services.save_calculation_record(product, inputs, results, user)
  │   Persists CalculationRecord
  │
  ├──► analytics.services.track_event('calculation.completed', properties)
  │
  ▼
Response (JSON or HTML) returned to browser
```

