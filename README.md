# Commercial Online Calculator Platform

A scalable, commercial online calculator platform built as a **modular Django monolith**.

The platform powers high-precision commercial calculator products:

| Product | Slug |
|---|---|
| **Talking Flyer Calculator** | `talking-flyer-calculator` |
| **AI Video Generation Calculator** | `ai-video-calculator` |

---

## Documentation

| Document | Description |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Application responsibilities, dependency rules, and system data flows |
| [docs/DEVELOPMENT_STANDARDS.md](docs/DEVELOPMENT_STANDARDS.md) | Service-layer conventions, data standards, model rules, and testing approach |
| [docs/DOMAIN_CONTRACTS.md](docs/DOMAIN_CONTRACTS.md) | Calculation engine, payment gateway, and entitlement access-check contracts |

---

## Technology Stack

| Component | Technology |
|---|---|
| Language | Python 3.14 |
| Framework | Django 6.1 |
| Database (production) | PostgreSQL via `psycopg` 3 |
| Database (local fallback) | SQLite (when `USE_POSTGRES=False`) |
| Environment variables | `python-dotenv` |
| Frontend | Semantic HTML5, plain CSS, vanilla JavaScript |
| Cache / queue | Redis — planned for a future task |

---

## Architecture Principles

- **Modular monolith.** Nine domain applications under `apps/`, each with clear ownership.
- **Service layer pattern.** Business logic lives in `services.py` modules. Views handle only HTTP concerns.
- **Decoupled payment gateways.** Provider adapters (`apps/payments/gateways/`) implement `BasePaymentGateway` and are isolated from domain business logic.
- **Decoupled calculation engines.** Engine classes (`apps/calculators/engines/`) implement `BaseCalculationEngine` and have no Django dependencies.
- **Entitlement access control.** Product access is enforced exclusively through `entitlements.services.user_has_product_access()`.
- **No hardcoded secrets.** All credentials and environment-sensitive values come from environment variables.
- **Safe local development.** When `USE_POSTGRES=False`, the development settings fall back to SQLite automatically.

---

## Project Structure

```
video_calculator/
├── .env.example                      # Template for environment variables
├── .env                              # Active local config (not committed)
├── .gitignore
├── manage.py
├── README.md
├── requirements/
│   ├── base.txt                      # Django, python-dotenv, psycopg[binary]
│   ├── development.txt               # -r base.txt
│   └── production.txt                # -r base.txt + gunicorn
├── requirements.txt                  # → requirements/development.txt
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DEVELOPMENT_STANDARDS.md
│   └── DOMAIN_CONTRACTS.md
├── videocalculatorproject/
│   ├── urls.py                       # Root URL dispatcher
│   ├── asgi.py                       # ASGI (production)
│   ├── wsgi.py                       # WSGI (production)
│   └── settings/
│       ├── base.py                   # Shared settings, app list, AUTH_USER_MODEL
│       ├── development.py            # Debug=True, console email, SQLite fallback
│       └── production.py             # PostgreSQL enforced, security headers
├── apps/
│   ├── accounts/                     # Custom User model (email auth)
│   ├── products/                     # Product catalogue
│   ├── orders/                       # Order lifecycle
│   ├── payments/                     # Payment records + provider gateway interface
│   │   └── gateways/                 # BasePaymentGateway and future provider adapters
│   ├── entitlements/                 # Product access control
│   ├── devices/                      # Device fingerprinting and session security
│   ├── calculators/                  # Calculation records + engine interface
│   │   └── engines/                  # BaseCalculationEngine and future engines
│   ├── notifications/                # Transactional alerts
│   └── analytics/                    # Event tracking
├── templates/
│   ├── base.html
│   └── pages/
│       └── home.html
├── static/
│   ├── css/main.css
│   ├── js/main.js
│   └── images/
└── media/
```

---

## Getting Started

### Prerequisites

- Python 3.12 or later (the project uses 3.14)
- `git`
- PostgreSQL (optional for local development — SQLite is the safe default)

### 1. Activate the virtual environment

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env`. Key settings:

| Variable | Default | Description |
|---|---|---|
| `DEBUG` | `True` | Set `False` in production |
| `SECRET_KEY` | (insecure placeholder) | Set a long random string in production |
| `USE_POSTGRES` | `False` | Set `True` to use PostgreSQL locally |
| `DB_NAME` | `videocalculator_db` | PostgreSQL database name |
| `DB_USER` | `postgres` | PostgreSQL user |
| `DB_PASSWORD` | `postgres` | PostgreSQL password |
| `DB_HOST` | `localhost` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |

### 4. Run migrations

```bash
python manage.py migrate
```

### 5. Create a superuser

```bash
python manage.py createsuperuser
# Prompts for email address and password (no username)
```

### 6. Start the development server

```bash
python manage.py runserver
```

- Home page: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- Talking Flyer Narration Test Page: [http://127.0.0.1:8000/calculators/talking-flyer/narration-test/](http://127.0.0.1:8000/calculators/talking-flyer/narration-test/)
- Universal Clip Planner Test Page: [http://127.0.0.1:8000/calculators/talking-flyer/clip-planner-test/](http://127.0.0.1:8000/calculators/talking-flyer/clip-planner-test/)
- Django admin: [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)

---

## Talking Flyer Narration & Speech Timing Engine (Task 003)

The platform provides a standalone, stateless speech timing and narration analysis engine:

- **Interactive Test Page**: `/calculators/talking-flyer/narration-test/`
- **Authoritative JSON API**: `/calculators/talking-flyer/narration-test/calculate/` (POST)
- **Calculation Formula**:
  $$\text{Duration (seconds)} = \left(\frac{\text{Word Count}}{\text{WPM}}\right) \times 60$$
- **Deterministic Word Counting**: Whitespace-separated tokens with tabs, multiple spaces, and newlines normalized; attached punctuation does not increase word count.
- **Speaking Speed Presets**:
  - Relaxed (120 WPM)
  - Conversational (135 WPM - default)
  - Brisk (150 WPM)
  - Fast (165 WPM)
  - Very fast (180 WPM)
  - Custom WPM: validated between 60 and 240 WPM

---

## Universal Clip Planning Engine & Narration Segmenter (Task 004)

Provider-independent clip planning engine operating on whole-word capacities to find the globally optimal combination and sequence of video clip durations:

- **Interactive Test Page**: `/calculators/talking-flyer/clip-planner-test/`
- **Authoritative JSON API**: `/calculators/talking-flyer/clip-planner-test/calculate/` (POST)
- **Optimisation Hierarchy**:
  1. *Minimise Clip Count*: Finds the minimum number of clips required to fit all words.
  2. *Minimise Total Generated Duration*: Selects the shortest valid duration among tied clip counts.
  3. *Minimise Total Reserved Duration*: Prefers options with less reserved time.
  4. *Deterministic Tie-Breaking*: Considers longer clips first when all prior values tie.
- **Clip Capacity Formula**:
  $$\text{Capacity} = \left\lfloor (\text{Duration} - \text{Reserved}) \times \frac{\text{WPM}}{60} \right\rfloor$$
- **Sentence-Boundary Segmentation**: Scans for terminal punctuation (`.`, `?`, `!`, `...`) in the final 20% of clip capacity, guaranteeing remaining words fit into subsequent clips without exceeding capacity.
- **100% Integrity Guarantee**: Verifies that reconstructed segments perfectly reproduce original normalised text with no missing, duplicated, or altered words.
- **Export Formats**: Copy complete JSON plan, copy formatted script segments, download plan as JSON, and download detailed breakdown as CSV.

---

## Running Tests

```bash
# Full test suite
python manage.py test

# Calculator domain tests (Narration + Clip Planning + Segmentation)
python manage.py test apps.calculators

# Single application
python manage.py test apps.accounts

# Django system checks
python manage.py check
```

The test suite currently covers:

| Test file | Coverage |
|---|---|
| `apps/accounts/tests/test_models.py` | User model creation, normalisation, superuser constraints |
| `apps/accounts/tests/test_services.py` | `register_user`, `deactivate_user` service functions |
| `apps/calculators/tests/test_narration.py` | Text normalisation, word counting rules, WPM validation, duration arithmetic, NarrationEngine contract, web view, and JSON calculation API |
| `apps/calculators/tests/test_clip_planning.py` | Clip capacity calculations, DP sequence optimisation, priority tie-breaking, summary metrics, UniversalClipPlanningEngine contract, and API endpoint |
| `apps/calculators/tests/test_narration_segmentation.py` | Single/multiple clip segmentation, sentence-boundary preference & fallback, punctuation preservation, remaining capacity protection, and text integrity validation |
| `videocalculatorproject/tests/test_project_setup.py` | Settings configuration, installed apps, home page |

> **Standard:** Every business-critical service function must have automated tests
> before the corresponding feature is merged. See
> [docs/DEVELOPMENT_STANDARDS.md §5](docs/DEVELOPMENT_STANDARDS.md#5-testing-conventions).

---

## Application Responsibilities (summary)

| Application | Owns | Calls into |
|---|---|---|
| `accounts` | User identity and lifecycle | — |
| `products` | Product catalogue and slugs | — |
| `orders` | Order creation and status transitions | `accounts` |
| `payments` | Payment records, gateway adapters | `orders`, `entitlements`, `notifications` |
| `entitlements` | Product access grants and validity checks | `accounts`, `products` |
| `devices` | Device fingerprinting and trust | `accounts` |
| `calculators` | Calculation records, narration engine, speech timing | `accounts`, `products`, `entitlements` |
| `notifications` | Transactional alerts | `accounts` |
| `analytics` | Append-only event tracking | `accounts` |

Full responsibility boundaries: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## Architectural Decisions & Platform Context

The following decisions have been confirmed:

| # | Topic | Decision | Implementation Status |
|---|---|---|---|
| 1 | **Product Slugs** | `talking-flyer-calculator` & `ai-video-calculator` | Confirmed as canonical identifiers |
| 2 | **Payment Provider** | Nestuge or Sella | Decoupled via `BasePaymentGateway`; adapter to be implemented in payments task |
| 3 | **Currency** | Multi-currency platform | Database models store ISO 4217 code and Decimal amounts |
| 4 | **Entitlement Model** | Lifetime (one-time purchase) | `Entitlement` supports indefinite access (`expires_at=None`) |
| 5 | **Calculator Access** | Gated behind paid entitlement | Public interactive test page provided for Task 003 validation; gated decorators apply to production calculators |

---

## Development Conventions (quick reference)

- **Services, not fat views.** Call services from views; never query the database in views.
- **Decimal for money.** `from decimal import Decimal` — never `float`.
- **UTC timestamps.** Use `django.utils.timezone.now()` everywhere.
- **UUID primary keys.** All custom models use `UUIDField(primary_key=True)`.
- **`update_fields` on saves.** Specify which fields are being saved.
- **`transaction.atomic()`** for multi-step writes.
- **No secrets in code.** All credentials come from environment variables.

Full standards: [docs/DEVELOPMENT_STANDARDS.md](docs/DEVELOPMENT_STANDARDS.md)
