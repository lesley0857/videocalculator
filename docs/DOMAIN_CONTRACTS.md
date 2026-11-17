# Domain Contracts

**Project:** Commercial Online Calculator Platform  
**Last updated:** 2026-11-07  

This document defines the **interface contracts** that all future implementation
work must respect. It describes what a component must accept, produce, and
guarantee — without dictating implementation details.

---

## Table of Contents

1. [Calculation engine contract](#1-calculation-engine-contract)  
2. [Payment gateway contract](#2-payment-gateway-contract)  
3. [Entitlement access-check contract](#3-entitlement-access-check-contract)  
4. [Product slug registry](#4-product-slug-registry)  

---

## 1. Calculation engine contract

### 1.1 Purpose

A calculation engine encapsulates all mathematical logic for one product. It is a
pure Python component with no Django dependencies. The engine is instantiated by
the calculator service layer, which provides validated inputs and stores the results.

### 1.2 Interface

All engines must implement `BaseCalculationEngine` from
`apps.calculators.engines.base`:

```python
from abc import ABC, abstractmethod
from typing import Any, Dict

class BaseCalculationEngine(ABC):

    @abstractmethod
    def calculate(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the core computation.

        Parameters
        ----------
        inputs : dict
            Validated input parameters. Keys and expected types are
            defined per-engine (see §1.4).

        Returns
        -------
        dict
            Structured result payload. Keys and types are defined
            per-engine (see §1.4).

        Raises
        ------
        ValueError
            If inputs fail domain-level validation rules
            (e.g., negative quantities, zero unit price).
        """
```

### 1.3 Engine guarantees

An engine implementation **must** guarantee:

| Guarantee | Detail |
|---|---|
| Determinism | Same inputs always produce the same outputs. |
| No side effects | The engine must not write to the database, dispatch emails, or call external APIs. |
| No Django imports | Engines import only from the Python standard library and `decimal.Decimal`. |
| Self-contained validation | Engines validate their own inputs and raise `ValueError` with a human-readable message if inputs are invalid. |
| Decimal arithmetic | All monetary arithmetic uses `decimal.Decimal`. Never `float`. |
| Structured output | The return dict always contains the same set of keys regardless of input values. |

### 1.4 Per-engine input / output schema

Each concrete engine documents its input schema and output schema in a docstring
and in the corresponding test file.

| Product | Engine class | Input schema | Output schema |
|---|---|---|---|
| Talking Flyer Narration Engine | `NarrationEngine` | `text: str`, `wpm: int \| str` | `word_count: int`, `wpm: int`, `duration_seconds: Decimal`, `duration_minutes: Decimal`, `duration_display: str`, `duration_readable: str`, `normalized_text: str` |
| Universal Clip Planning Engine | `UniversalClipPlanningEngine` | `narration: str`, `wpm: int \| str`, `clip_options: list[dict]`, `segmentation: dict` | `success: bool`, `narration: dict`, `plan: dict`, `clips: list[dict]`, `validation: dict` |
| AI Video Generation Calculator | `AIVideoEngine` | _TBD in future tasks_ | _TBD in future tasks_ |

### 1.5 How the service layer uses the engine

```python
# apps/calculators/services.py

def run_calculation(
    engine: BaseCalculationEngine,
    product: Product,
    raw_inputs: Dict[str, Any],
    user: Optional[User] = None,
) -> CalculationRecord:
    """
    Runs the engine and persists the result. This function is the
    boundary between the Django application and the pure engine.
    """
    results = engine.calculate(raw_inputs)          # may raise ValueError
    return save_calculation_record(
        product=product,
        inputs=raw_inputs,
        results=results,
        user=user,
    )
```

**The view** catches `ValueError` and returns a 400 response.  
**The service** does not catch `ValueError` — it propagates up.

### 1.6 Testability requirement

Every engine must ship with test coverage that tests:
- At least one happy-path case that asserts all output keys and their types.
- At least one case for each documented validation error.
- At least one edge-case (e.g., minimum inputs, zero optional fields).

### 1.7 Talking Flyer Narration Engine Specification (Task 003)

#### Purpose
Accepts promotional or flyer narration text, normalises whitespace, calculates total
word count deterministically, validates speaking speed, and computes estimated speech
duration.

#### Word-count convention
Words are whitespace-separated tokens after full whitespace normalisation (newlines, tabs,
consecutive spaces collapsed). Punctuation attached to words does not increment word counts.
Hyphenated words remain single whitespace-separated tokens.

- `"Hello world"` = 2 words
- `"Hello    world"` = 2 words
- `"Hello\nworld"` = 2 words
- `"Hello, world!"` = 2 words
- `"Well-known technology"` = 2 words

#### Speaking speed presets & bounds
- **Relaxed**: 120 WPM (slow, deliberate delivery)
- **Conversational**: 135 WPM (natural, balanced delivery; default)
- **Brisk**: 150 WPM (moderately fast delivery)
- **Fast**: 165 WPM (fast narration)
- **Very fast**: 180 WPM (rapid promotional delivery)
- **Custom range**: Enforced between 60 WPM (minimum) and 240 WPM (maximum).

#### Duration formula & numerical precision
$$\text{Duration (seconds)} = \left(\frac{\text{Word Count}}{\text{WPM}}\right) \times 60$$

- All internal calculations use `decimal.Decimal` to avoid floating-point drift.
- Displayed `duration_seconds` and `duration_minutes` are rounded using `ROUND_HALF_EVEN` to 2 decimal places.
- `duration_display` formats as `MM:SS` (e.g. `01:35`).
- For empty narration, the engine returns 0 words and 0.00 seconds without raising an error.

#### Boundary between Task 003 and Task 004 (Clip Planning)
- **Task 003** focuses strictly on text normalisation, word counting, and speech duration estimation. It does NOT impose arbitrary word caps (such as 19 or 20 words) or uncalibrated pause allowances.
- **Task 004** consumes the outputs from this service (`word_count`, `duration_seconds`, `wpm`) alongside platform clip duration capabilities (e.g., 5s, 8s, 10s, 15s, 20s, 30s) to perform universal multi-clip planning.

### 1.8 Universal Clip Planning & Segmentation Contract (Task 004)

#### Purpose
The Universal Clip Planning Engine receives verified narration timing outputs and determines:
1. Total video clips required.
2. The optimal combination and sequence of available clip durations.
3. Complete-word capacity and assigned narration words per clip.
4. Continuous 1-based word ranges and segmented narration text.
5. Speech, reserved, and unused video duration per clip and across the plan.
6. Overall and per-clip utilisation percentages.

The engine is **provider-agnostic**: it contains zero hardcoded assumptions about specific AI video generators (Runway, Kling, Veo, Sora, Pika).

#### Clip Capacity Calculation
$$\text{Words per second} = \frac{\text{WPM}}{60}$$
$$\text{Available narration duration} = \text{Generated duration} - \text{Reserved duration}$$
$$\text{Complete-word capacity} = \left\lfloor \text{Available narration duration} \times \frac{\text{WPM}}{60} \right\rfloor$$

- Complete-word capacity is an integer floor. Partial words are never allocated to clips.
- A clip option with zero word capacity is automatically excluded from selection.

#### Optimisation Priorities & Dynamic Programming
The planner employs a 1D Dynamic Programming approach tracking exact accumulated word capacity:
1. **FIRST**: Minimise total number of clips ($k$).
2. **SECOND**: Minimise total generated video duration ($\sum d_i$) among plans with identical clip counts.
3. **THIRD**: Minimise total reserved duration ($\sum r_i$) among tied plans.
4. **FOURTH**: Deterministic tie-breaking: prefer longer clip options first when all previous values are equal.

#### Narration Segmentation & Sentence Boundaries
- The segmentation service segments the normalised text in strictly sequential order.
- Words are never altered, duplicated, or dropped.
- Sentence boundary scanning checks whether terminal punctuation (`.`, `?`, `!`, `...`) exists within the final window of the clip's capacity (default: final 20%).
- If a sentence boundary exists and remaining words can still fit into subsequent clips without exceeding their capacities, the segment breaks on the sentence boundary.
- If no boundary is found, the segment takes maximum available capacity.
- **Integrity Validation**: Reconstructed text is verified against the original normalised text. If words are missing or text diverges, an internal integrity error is raised.

#### Complexity Limits
- Clip duration: 1 to 600 seconds.
- Max unique clip options per request: 50.
- Max clips per plan: 1,000.
- Max narration words: 50,000.

#### Boundary with Future Tasks (Task 005+)
- Task 004 is purely algorithmic and stateless. It does not integrate external AI video APIs, store projects in a database, generate audio, render video, or charge customer payments.
- Future tasks will connect these clip configurations to database-driven AI model profiles and automated video generation workflows.

---

## 2. Payment gateway contract

### 2.1 Purpose

A payment gateway adapter translates between the internal domain vocabulary and an
external payment provider's API. It is a thin translation layer — it makes HTTP
requests to the provider and returns plain Python dicts.

### 2.2 Interface

All gateway adapters must implement `BasePaymentGateway` from
`apps.payments.gateways.base`:

```python
from abc import ABC, abstractmethod
from typing import Any, Dict

class BasePaymentGateway(ABC):

    @abstractmethod
    def create_checkout_session(
        self,
        order_id: str,
        amount: str,
        currency: str,
    ) -> Dict[str, Any]:
        """
        Initiate a hosted checkout session with the provider.

        Parameters
        ----------
        order_id : str
            The UUID of the internal Order record (str form).
        amount : str
            The amount as a string representation of a Decimal,
            e.g. '29.99'. Never pass a float.
        currency : str
            ISO 4217 three-letter currency code, e.g. 'USD'.

        Returns
        -------
        dict with at minimum:
            {
                'checkout_url': str,          # URL to redirect the user to
                'provider_session_id': str,   # provider's own session reference
            }

        Raises
        ------
        PaymentGatewayError
            If the provider rejects the request or the network call fails.
        """

    @abstractmethod
    def handle_webhook(
        self,
        payload: bytes,
        signature: str,
    ) -> Dict[str, Any]:
        """
        Validate the webhook signature and parse the event payload.

        Parameters
        ----------
        payload : bytes
            The raw request body as received (required for signature
            verification).
        signature : str
            The provider's signature header value.

        Returns
        -------
        dict with at minimum:
            {
                'event': str,             # e.g. 'payment.succeeded', 'payment.failed'
                'provider_reference': str, # provider's transaction or charge ID
                'order_id': str,          # internal order UUID extracted from metadata
                'amount': str,            # amount as Decimal string
                'currency': str,          # ISO 4217 code
            }

        Raises
        ------
        PaymentGatewayError
            If the signature is invalid or the payload cannot be parsed.
        """
```

### 2.3 Gateway guarantees

| Guarantee | Detail |
|---|---|
| No model writes | Gateways never write to the database. |
| No business decisions | Gateways return raw data. The service layer decides what to do with it. |
| Signature validation | `handle_webhook` must always validate the provider's signature before parsing the payload. Reject unsigned or mis-signed payloads immediately. |
| Decimal amounts | Amounts in returned dicts are always `str` representations of Decimal values (not floats, not integers). |
| Idempotency metadata | The returned dict from `handle_webhook` must include the provider's own idempotency/reference ID so the service layer can detect duplicate events. |

### 2.4 Payment lifecycle and status mapping

The following lifecycle applies regardless of provider:

```
INITIATED
    │
    ├─► SUCCESSFUL  (webhook: payment.succeeded / charge.captured)
    │
    ├─► FAILED      (webhook: payment.failed / payment_intent.payment_failed)
    │
    └─► REFUNDED    (webhook: refund.created / charge.refunded)
```

Mapping between provider event names and internal `PaymentStatus` values is the
gateway adapter's responsibility. The service layer works only with internal status
values.

### 2.5 Webhook idempotency

The payment service layer must check whether a `reference_id` has already been
processed before updating the `Payment` and `Order` records. The gateway is
responsible for surfacing the reference; the service is responsible for the
idempotency check.

```python
# apps/payments/services.py (future implementation pattern)

def handle_provider_webhook(gateway: BasePaymentGateway, payload: bytes, signature: str):
    event = gateway.handle_webhook(payload, signature)   # may raise PaymentGatewayError
    reference_id = event['provider_reference']

    # Idempotency check — do not process the same event twice
    if Payment.objects.filter(reference_id=reference_id, status=PaymentStatus.SUCCESSFUL).exists():
        return  # already processed

    payment = Payment.objects.get(order__id=event['order_id'], status=PaymentStatus.INITIATED)
    if event['event'] == 'payment.succeeded':
        record_payment_success(payment, reference_id=reference_id, metadata=event)
    elif event['event'] == 'payment.failed':
        record_payment_failure(payment, failure_reason=event)
```

### 2.6 Pending transactions

A `Payment` remains in `INITIATED` status until a webhook confirms success or
failure. The platform must handle the following:

- User abandons the checkout page → `Payment` stays `INITIATED`, `Order` stays
  `PENDING`. A background job (future) can expire stale INITIATED records.
- Provider webhook arrives out of order → the idempotency check prevents double
  processing.
- Webhook delivery fails → providers retry; the idempotency check ensures safety.

### 2.7 Failed transactions

When `record_payment_failure()` is called:

- `Payment.status` → `FAILED`.
- `Payment.metadata` gains a `'failure'` key with the provider's reason object.
- `Order.status` remains `PENDING` (the user may retry with a new payment).
- A notification service call should be made to inform the user.

Do not transition `Order.status` to `CANCELLED` on payment failure alone — the
user may attempt another payment against the same order.

### 2.8 Selecting a provider (open decision)

No provider is selected yet. When a provider is selected:

1. Create `apps/payments/gateways/<provider>_gateway.py`.
2. Implement `BasePaymentGateway`.
3. Register the class name in a new setting:
   `PAYMENT_GATEWAY = 'apps.payments.gateways.stripe_gateway.StripeGateway'`
4. The service layer instantiates the gateway via Django's import machinery —
   views and services never reference a concrete gateway class directly.

---

## 3. Entitlement access-check contract

### 3.1 Purpose

The entitlement system enforces product access control. It provides a single public
function that all other applications must use to ask "can this user use this
product?".

### 3.2 Public API

```python
# apps/entitlements/services.py

def user_has_product_access(user: User, product_slug: str) -> bool:
    """
    Returns True if the user holds a currently valid entitlement for
    the product identified by product_slug.

    Parameters
    ----------
    user : User
        The user requesting access. If the user is not authenticated,
        returns False immediately.
    product_slug : str
        The canonical slug of the product, e.g.
        'talking-flyer-calculator' or 'ai-video-calculator'.

    Returns
    -------
    bool
        True  — user holds an active, unexpired entitlement.
        False — user is unauthenticated, holds no entitlement, or
                the entitlement has expired / been deactivated.
    """
```

### 3.3 Access-check rules

1. An entitlement is **valid** when both conditions are true:
   - `Entitlement.is_active` is `True`.
   - `Entitlement.expires_at` is `None` **or** `expires_at > timezone.now()`.

2. Products are **independent**. A paid entitlement for `'talking-flyer-calculator'`
   does not grant access to `'ai-video-calculator'`. Each product entitlement must
   be granted separately.

3. Revoking access uses `Entitlement.is_active = False`, not deletion.

4. Entitlement expiry is based on the UTC timestamp in `expires_at`. No timezone
   conversion is applied at the point of the check.

### 3.4 How other applications use the access check

**In a view:**

```python
from apps.entitlements.services import user_has_product_access

class CalculatorView(View):
    PRODUCT_SLUG = 'talking-flyer-calculator'

    def get(self, request):
        if not user_has_product_access(request.user, self.PRODUCT_SLUG):
            return redirect('products:list')
        ...
```

**In a service (less common — prefer the view level):**

```python
from apps.entitlements.services import user_has_product_access

def run_calculation(engine, product, inputs, user):
    if not user_has_product_access(user, product.slug):
        raise PermissionError("User does not have access to this product.")
    ...
```

### 3.5 Granting entitlements

Entitlements are granted by the payment service after a confirmed successful payment:

```python
# apps/payments/services.py
from apps.entitlements.services import grant_entitlement

def record_payment_success(payment, reference_id, metadata=None):
    with transaction.atomic():
        ...
        grant_entitlement(user=payment.order.user, product=payment.order.product)
```

No other application should call `grant_entitlement()` in normal flow. Admin staff
may grant entitlements through the Django admin interface.

### 3.6 What the entitlement contract does not define yet

- Quota limits (e.g., number of calculations per month).
- Trial / free-tier entitlements.
- Team or organisation-level entitlements.
- Grace periods after expiry.

These will be specified in a future task when the subscription model is designed.

---

## 5. AI video registry and Task 006 integration

The registry's stable relational identity is `Provider` → `VideoModel`. Each
`VideoModel` row represents one provider, model slug, and version; the database
uniqueness constraint is `(provider, slug, version)`. Future pricing records should
use a foreign key to the exact `VideoModel` version, and a `Workflow` foreign key
when a price differs by workflow. They must not copy provider/model names into
pricing tables. `PROTECT` keeps referenced identities available for historical
quotes and costs.

Capability keys are stable machine identifiers; a capability status is one of
`supported`, `not_supported`, `unknown`, or `not_verified`. Empty/unknown values are
not interpreted as false. An update to a capability creates a `CapabilityRevision`
containing the prior state. Evidence rows can be attached to a model or a specific
capability and carry classification, source, status, and verification time.

Read API: `GET /api/video-registry/providers/`,
`GET /api/video-registry/providers/<provider-slug>/`,
`GET /api/video-registry/models/?workflow=<slug>&capability=<key>`,
`GET /api/video-registry/models/<provider-slug>/<model-slug>/?version=<version>`,
and its `/capabilities/` subresource. `apps.video_registry.services` provides
`get_active_providers`, `get_active_models`, `get_model`, `filter_models`,
`get_native_talking_video_models`, `get_models_requiring_external_tts`, and
`get_models_requiring_external_lip_sync`. Invalid filter values raise `ValueError`;
views translate them to HTTP 400. Public responses omit administrative notes.

To add a provider, create it in Django Admin, create a `Workflow` when a new
workflow category is needed, then add each version as a separate `VideoModel`.
Associate only documented workflows and add explicit capability states plus
evidence. Do not create demonstration provider data in the production registry.

## 6. Task 006 pricing and cost contract

`ModelPricing.video_model` is a foreign key to the exact Task 005 model version;
`workflow` is an optional foreign key to its registered workflow. Provider identity
is obtained through `video_model.provider`; pricing does not duplicate the registry.
Model, operation, credit-package, and subscription prices are effective-dated and
their identity/rate fields are immutable after insertion. Add a new rate period to
change a price. `CostEstimate` snapshots the submitted inputs, the exact pricing
record identifiers and rates used, exchange-rate identifiers and rates, and the
serialized result.

Model price methods are fixed amount per generation, money per second, credits per
generation, and credits per second. Per-second values use the configured minimum
duration and round upward to the configured billing increment. Currency conversion
uses `1 BASE = rate QUOTE`; direct rates are preferred and inverse rates are
reciprocated. A rate older than seven days relative to the estimate's `as_of` time
makes the estimate incomplete. Final money is rounded to two decimals with
`ROUND_HALF_UP`; intermediate arithmetic uses `Decimal` without rounding.

Credit use is reported separately from its cash value. With a plan, marginal cash
cost prices only credits above the supplied remaining balance, while allocated
economic cost is `subscription price × consumed credits ÷ included credits`. The
caller selects `credit_cost_basis`; a missing balance or additional-credit price is
reported as missing. Without a plan, an applicable `CreditPackage` is required.
No CRD amount is treated as money without a package/add-on valuation.

For retries, `failed_attempt_billing` is `billable`, `free`, or `unknown`. Expected
retry allowance is priced with the configured billing rule. Unknown failed-attempt
billing leaves the known subtotal intact but makes the estimate incomplete. Actual
attempt inputs include successful and failed counts, which must sum to
`actual_attempts`. Estimates warn when a component exceeds three attempts; the
future production-job task owns persisting attempt events.

The engine's pure input is a normalized object containing model/pricing snapshots,
operations, FX-rate snapshots, output currency, retry data, and either
`markup_percentage` or `target_margin_percentage` (never both). Its output contains
component costs, known partial subtotal, quality warnings, completeness status,
production/retry costs, selling price, gross profit, and gross margin. Missing
required pricing or FX returns `incomplete`/HTTP 422 and never yields a complete
quote or a zero substituted for missing data.

Read endpoints are `/pricing/api/records/`, `/pricing/api/models/<video-model-uuid>/`,
`/pricing/api/exchange-rates/`, and `/pricing/api/operations/`. Submit JSON to
`POST /pricing/api/estimate/`; retrieve the stored audit snapshot at
`GET /pricing/api/estimates/<estimate-uuid>/`. The development calculator is
`/pricing/test/`; Admin records are under `/admin/pricing/`. The API accepts model,
workflow, operation, balance, currency, retry, markup, and margin identifiers/data,
but rejects client-supplied prices and exchange rates.

## 7. Task 007 user workspace and estimate history

`workspace.Project.owner` is a non-null foreign key to the configured custom user.
Project queries and API lookups are scoped by the authenticated owner. Projects
have `active` and `archived` states; archive/restore operations preserve the
project and its estimate history. New estimates are saved with both `owner` and
`project`, and the model validates that the project belongs to the owner.

`CostEstimate` keeps the Task 006 JSON input/result snapshot and timestamp, with
owner/project foreign keys. Migration `pricing.0003` adds nullable relations and a
constraint requiring both relations to be null or both present. This preserves any
pre-existing Task 006 rows without assigning an arbitrary owner. The current local
database had no estimate rows when this migration was applied. New estimate saves
require both relations; all ordinary-user estimate queries filter by owner and
exclude unassigned legacy rows.

The existing pricing engine remains the source of every new calculation. A saved
estimate contains resolved pricing/model details and exchange-rate data in its
result snapshot. Opening or comparing it reads that snapshot and never recalculates
against current rates. Recalculation from a prior estimate is an explicit action
that creates a new record and clears the previous pricing-record selections so the
new request resolves current effective pricing. It does not overwrite the source.

Project dashboard/list/detail pages live under `/workspace/`. Browser project
operations use authenticated views and CSRF-protected forms. JSON APIs are:

- `GET/POST /workspace/api/projects/` — owner-scoped, paginated project list/create.
- `GET/PATCH /workspace/api/projects/<project-uuid>/` — read or rename/update description.
- `POST /workspace/api/projects/<project-uuid>/archive/` — archive or restore using
  `{"archived": true|false}`.
- `GET/POST /workspace/api/projects/<project-uuid>/estimates/` — history or calculate
  and save an estimate in that project.
- `GET /workspace/api/estimates/<estimate-uuid>/` — retrieve the owner's saved snapshot.
- `POST /workspace/api/estimates/compare/` — compare 2–10 estimates owned by the caller.
- `POST /pricing/api/estimate/` — public callers may calculate without a
  `project_id`; those results are not persisted. Authenticated users can include
  an owner-owned active `project_id` to save an immutable snapshot.
- `GET /pricing/api/estimates/<estimate-uuid>/` — retained Task 006 detail route, now
  authenticated and owner-scoped.

Foreign and unassigned legacy project/estimate identifiers return the same `not_found`
response. Owner IDs are never accepted from the client. Comparisons preserve each
estimate's original currency and exchange-rate snapshot; totals in different
currencies are displayed separately without a live or current-rate conversion.

`CostEstimate.save()` blocks edits to existing snapshots and the Admin denies
estimate add/change/delete. This is application-level protection; it is not a
database trigger and direct SQL or bulk ORM mutation can bypass it. The generic
legacy estimate has no owner/project and is not available through ordinary-user
API or workspace queries.

The API may accept caller-supplied `actual_attempts`, `successful_attempts`, and
`failed_attempts` as costing inputs, consistent with Task 006. The estimate UI and
detail view label such values as user-supplied assumptions; they are not provider
observations or platform-tracked activity. Task 007 creates no attempt/job records.

## 8. Task 008 customer-facing calculator experience

`/products/` and `/calculators/` are HTML directories. Public tools include the
narration calculator, clip planner, and `/pricing/test/` production cost form.
The existing narration and clip engines remain authoritative; narration inputs
are passed between their pages using browser session storage. After a successful
clip plan, the cost calculator can receive the clip count and average generated
duration as editable assumptions. That average is not a replacement for a
heterogeneous clip breakdown: users can add separate pricing components and
select model/workflow assumptions independently.

The cost page's provider/model options use active registry records. Model
versions are shown separately, workflows are those explicitly related to the
selected version, and capability statuses/verification details are displayed
from the model detail endpoint. Unknown capability values are displayed as
unknown and are never rendered as supported. An empty provider, model, workflow,
effective price, or FX registry produces an explicit empty/incomplete state.
Pricing choices and calculation results come from the existing Task 006 read and
estimate endpoints; browser code does not calculate money. Optional service
costs require configured operation-pricing records. No contingency field is
exposed because the current engine has no contingency input.

Public visitors may submit a valid request to `POST /pricing/api/estimate/` with
the same Task 006 cost fields but without `project_id`; this calculates without
creating a `CostEstimate`. A visitor can retain their form values in same-origin
session storage while navigating to sign in or register. Once authenticated,
recalculating with an active project ID uses the existing owner-scoped save path
and creates a new immutable snapshot. The server never trusts a client owner ID.
Historical comparisons continue to use Task 007 `compare_estimates`; mixed
currencies remain separate and saved FX snapshots are preserved.

Local customer pages: `/products/`, `/calculators/`,
`/calculators/talking-flyer/narration-test/`,
`/calculators/talking-flyer/clip-planner-test/`, and `/pricing/test/`. Administrators
must configure active provider/model/workflow records, effective model and
optional-operation pricing, applicable credit packages or subscription plans,
and FX records before complete estimates can be produced. No commercial pricing
is fabricated or seeded by this task. Payment integrations (Nestuge/Selar),
checkout, entitlements, generation APIs, TTS/lip-sync execution, rendering, and
production-job tracking remain out of scope.

## Talking Flyer production costing extension

The existing customer calculator at `/pricing/test/` accepts configured model versions and exact generation configuration (resolution, aspect ratio, audio mode, and duration). Configuration choices are accepted only when the registry marks the matching capability as supported. Model prices are effective-dated and scoped to their configuration.

Production tools (such as ChatGPT, CapCut, and voice services) are separate from generation models and workflows. A tool can carry activities, subscription allocation, included usage, and additional usage pricing. Select each tool once per estimate so a shared subscription is allocated once. Subscription allocations are economic cost; cash expenditure is reported separately, including a full subscription purchase only when selected for this project.

Production overheads support electricity, internet/data, labour, equipment, software, licensed assets/music, storage/delivery, payment and FX fees, taxes/duties, and other expenses. Administrators configure effective-dated rates. A customer may instead enter a manual project amount, which is labelled as a customer estimate. Missing rates remain incomplete rather than being treated as zero.

The result reports desired final duration, expected usable footage, billable generated duration, AI/provider costs, optional services, production tools, overheads, cost per finished video and finished second, and additional cash expenditure. Each saved estimate retains its submitted inputs, selected effective prices, evidence, FX rates, and calculated result as an immutable historical snapshot.

Pricing is not seeded automatically. Configure the registry in Django Admin after reviewing current provider and local subscription prices. Veo API prices depend on model variant, output resolution, duration, and audio mode; subscription prices such as CapCut vary by region and account. See [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing), [ChatGPT Plus details](https://help.openai.com/en/articles/6950777-what-is-chatgpt-plus), [ElevenLabs API pricing](https://elevenlabs.io/pricing/api), and [CapCut Pro pricing help](https://www.capcut.com/help/how-much-does-capcut-pro-cost) when configuring rates.

## Specialty catalogue and calculator request contracts

The provider catalogue is normalized independently from the platform retail
`products.Product` table. `Specialty` classifies providers, offerings, and plans;
`ProviderOffering` identifies a provider product or service; `AccessRoute` identifies
how that offering is reached and billed. Versioned `VideoModel` rows stay attached
to their existing provider and may be linked to offerings. Routes list applicable
model versions explicitly. No real-world provider, plan, model capability, or price
is inferred by the specialty seed migration.

Read-only catalogue endpoints are mounted below `/api/video-registry/`:

- `specialties/`
- `specialties/<slug>/providers/`
- `offerings/?specialty=<slug>&provider=<slug>`
- `plans/?specialty=<slug>&offering=<uuid>`
- `access-routes/?specialty=<slug>&offering=<uuid>[&model=<uuid>]`
- `models/?specialty=<slug>&provider=<slug>&offering=<uuid>&access_route=<uuid>`
- `models/<provider>/<model>/capabilities/?version=<version>`

The estimate endpoint accepts `calculator_type` (`talking_flyer`,
`video_generation`, or backward-compatible `general`). Product-specific requests
use version 1 contracts in `apps/pricing/contracts.py`. A Talking Flyer request
passes `talking_flyer.schema_version`, narration values, and an exact consecutive
`clip_plan.clips` list; every clip carries generated, reserved, and usable seconds
and word counts. Its component `clip_sequences` assignments must allocate every
clip exactly once. Video Generation passes `video_generation.schema_version`, a
brief, script preparation method, optional scriptwriting tool selection, and ordered
scenes. These are backend contracts; customer interfaces and AI generation/API
integrations are outside this implementation.

Saved estimates record their calculator type and a resolved catalogue/pricing/FX
snapshot. Detail reads use that stored snapshot and do not re-resolve current rates.
The customer-facing Talking Flyer journey is mounted at `/calculators/talking-flyer/`;
it composes the existing narration and clip-plan endpoints with specialty catalogue
selection and the shared estimate endpoint. Guest calculations remain transient.
When saving, a server-validated request is held in the authenticated session until
the owner chooses an active project or creates one. Registration and login return to
that save step. Reusing a saved Talking Flyer estimate restores its script and speed
as a starting point; current models and prices must be selected and recalculated.

## 4. Product slug registry

The following slugs are the canonical identifiers for the initial two products.
They must be used consistently across all applications, test fixtures, and
configuration.

| Product | Slug | Status |
|---|---|---|
| Talking Flyer Calculator | `talking-flyer-calculator` | Active |
| AI Video Generation Calculator | `ai-video-calculator` | Active |

These slugs must be created in the database via a Django data migration or
management command before any application logic that references them by slug
can function correctly. That migration or command will be created in the task
that implements the product catalogue.

> **Decision required (see §Unresolved Decisions in README):** Confirm whether
> the product slugs above match your planned product naming before Task 003.

