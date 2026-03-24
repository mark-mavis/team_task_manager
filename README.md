# TaskForge

A small, production-style task management web app built to teach **Python testing frameworks** thoroughly. The codebase is intentionally simple enough for one developer to read end-to-end, while following real-world patterns for structure, auth, database access, and testing.

---

## Technology stack

| Layer | Choice |
|---|---|
| Backend | FastAPI |
| Templates | Jinja2 (server-rendered HTML) |
| Database | SQLAlchemy 2 + SQLite (swap to Postgres with one env var) |
| Auth | Session cookies via Starlette SessionMiddleware |
| Tests | pytest, httpx TestClient, Playwright |

---

## Local setup

### 1. Create and activate a virtual environment

```bash
# Create
python -m venv .venv

# Activate – macOS / Linux
source .venv/bin/activate

# Activate – Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Activate – Windows (Command Prompt)
.venv\Scripts\activate.bat
```

### 2. Install dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
# Edit .env and set SECRET_KEY to a long random string
```

Generate a secure key:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 4. Seed the database with demo data

```bash
python scripts/seed.py
```

Demo accounts created by the seed script:

| Username | Password | Role |
|---|---|---|
| `admin` | `password123` | admin |
| `alice` | `password123` | member |
| `bob` | `password123` | member |

### 5. Run the development server

```bash
python -m uvicorn app.main:app --reload
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

---

## Running the tests

### Unit tests only

```bash
python -m pytest tests/unit -v
```

### Integration tests only

```bash
python -m pytest tests/integration -v
```

### Unit + integration (default, no browser required)

```bash
python -m pytest tests/unit tests/integration
```

### End-to-end browser tests (Playwright)

Install the Chromium browser first (one-time):
```bash
python -m playwright install chromium
```

Then run:
```bash
python -m pytest tests/e2e -v
```

### All tests

```bash
python -m pytest tests/ -v
```

### Coverage report

```bash
python -m pytest tests/unit tests/integration --cov=app --cov-report=term-missing --cov-report=html
# Open htmlcov/index.html in a browser
```

---

## Makefile shortcuts

If you have `make` available:

```bash
make install          # pip install -r requirements.txt
make dev              # uvicorn --reload
make seed             # python scripts/seed.py
make test             # unit + integration
make test-unit        # unit only
make test-integration # integration only
make test-e2e         # Playwright browser tests
make test-coverage    # with HTML coverage report
make playwright-install  # install Chromium for e2e
```

---

## Project structure

```
taskforge/
├── app/
│   ├── main.py          # FastAPI app factory, middleware, router registration
│   ├── config.py        # Settings from environment variables (pydantic-settings)
│   ├── db.py            # SQLAlchemy engine, session factory, Base, get_db dependency
│   ├── models/          # SQLAlchemy ORM models (User, Task, TaskEvent)
│   ├── schemas/         # Pydantic request/response schemas and form validators
│   ├── routes/          # FastAPI routers (auth, dashboard, tasks)
│   ├── services/        # Business logic – all DB writes go through here
│   ├── auth/            # Session dependency helpers (get_current_user, require_admin)
│   ├── templates/       # Jinja2 HTML templates
│   └── static/          # CSS
├── tests/
│   ├── conftest.py      # Shared fixtures: DB engine, TestClient, user/task factories
│   ├── unit/            # Service-layer tests (no HTTP)
│   ├── integration/     # Full HTTP round-trips via FastAPI TestClient
│   └── e2e/             # Real browser tests via Playwright
├── scripts/
│   └── seed.py          # Demo data seeder
├── .env.example
├── Dockerfile
├── Makefile
├── pytest.ini
└── requirements.txt
```

---

## Testing strategy

TaskForge is structured as a **three-layer test suite**. Each layer teaches different pytest skills and covers a different part of the stack.

### Layer 1 – Unit tests (`tests/unit/`)

**What they test:** Pure Python functions and service-layer logic in isolation.
No HTTP, no routing, minimal database (in-memory SQLite).

**What you learn:**
- Writing focused tests with clear **Arrange / Act / Assert** structure
- `@pytest.mark.parametrize` for testing many inputs with one test function
- `monkeypatch` to replace internal dependencies (e.g. `datetime.now`, `verify_password`)
- Testing edge cases without spinning up the whole app

**Key files:**
- `tests/unit/test_auth_service.py` – password hashing, authentication logic
- `tests/unit/test_task_service.py` – CRUD, permission helpers, audit events, stats

---

### Layer 2 – Integration tests (`tests/integration/`)

**What they test:** Full HTTP request/response cycles using FastAPI's `TestClient`.
Every route, redirect, status code, and rendered HTML is verified.

**What you learn:**
- **FastAPI dependency overrides** – swapping `get_db` for a test session
- **Isolated test database** – per-test transaction rollback so tests never interfere
- Testing **authentication and authorization** at the HTTP layer
- Testing **form submissions**, redirects, and error states
- `@pytest.mark.parametrize` for permission matrix testing (admin vs member)

**Key files:**
- `tests/integration/test_auth_routes.py` – login/logout flows, session management
- `tests/integration/test_task_routes.py` – CRUD endpoints, permission enforcement
- `tests/integration/test_dashboard_routes.py` – stat card rendering

**How the database isolation works:**

```
Session-scoped engine  (created once for the whole test run)
  └── Per-test connection
        └── Begin transaction
              └── Test runs against this transaction
        └── Rollback — database is clean for the next test
```

This is much faster than recreating tables for every test.

---

### Layer 3 – End-to-end tests (`tests/e2e/`)

**What they test:** Real user flows in a real Chromium browser, against a live server
started in a background thread.

**What you learn:**
- Using **Playwright for Python** with `pytest-playwright`
- `expect()` assertions for visible elements and URL changes
- Spinning up a live server in a `module`-scoped fixture
- `data-testid` attributes as **stable selectors** (don't break when CSS changes)
- The difference between unit/integration mocking and true end-to-end verification

**Key file:** `tests/e2e/test_browser.py`

---

### Fixture design (`tests/conftest.py`)

The `conftest.py` is worth reading carefully – it demonstrates the core patterns:

| Fixture | Scope | Purpose |
|---|---|---|
| `engine` | session | One in-memory DB for the whole run |
| `db` | function | Per-test session wrapped in a rollback transaction |
| `client` | function | TestClient with `get_db` overridden |
| `admin_user` / `member_user` | function | Pre-created users via `make_user()` factory |
| `admin_client` / `member_client` | function | Authenticated clients ready to use |
| `sample_task` | function | Pre-created task via `make_task()` factory |

The `make_user()` and `make_task()` **factory helpers** (not fixtures) are importable
by any test file, giving you fine-grained control when you need unusual combinations.

---

## Roles and permissions

| Action | admin | member |
|---|---|---|
| View tasks | ✅ | ✅ |
| Create tasks | ✅ | ✅ |
| Edit any task | ✅ | ❌ |
| Edit own assigned task | ✅ | ✅ |
| Delete tasks | ✅ | ❌ |

---

## Switching to PostgreSQL

Change one line in `.env`:

```
DATABASE_URL=postgresql://user:password@localhost:5432/taskforge
```

Then install the driver:
```bash
python -m pip install psycopg2-binary
```

No code changes required — SQLAlchemy handles the rest.
