# TaskForge Makefile
# Assumes you have activated your virtual environment before running these commands.

.PHONY: help install dev seed test test-unit test-integration test-e2e \
        test-coverage lint docker-build docker-run clean

PYTHON  = python
PYTEST  = python -m pytest
UVICORN = python -m uvicorn

help:          ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Setup ──────────────────────────────────────────────────────────────────

install:       ## Install all dependencies into the active virtual environment
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

playwright-install:  ## Install Playwright browsers (required for e2e tests)
	$(PYTHON) -m playwright install chromium

# ── Running the app ────────────────────────────────────────────────────────

dev:           ## Run the development server with auto-reload
	$(UVICORN) app.main:app --reload --host 127.0.0.1 --port 8000

seed:          ## Seed the database with demo data
	$(PYTHON) scripts/seed.py

# ── Testing ────────────────────────────────────────────────────────────────

test:          ## Run all tests (unit + integration, excluding e2e)
	$(PYTEST) tests/unit tests/integration

test-unit:     ## Run unit tests only
	$(PYTEST) tests/unit -v

test-integration: ## Run integration tests only
	$(PYTEST) tests/integration -v

test-e2e:      ## Run end-to-end Playwright browser tests
	$(PYTEST) tests/e2e -v

test-all:      ## Run every test including e2e
	$(PYTEST) tests/ -v

test-coverage: ## Run tests with HTML coverage report
	$(PYTHON) -m pytest tests/unit tests/integration \
	  --cov=app --cov-report=term-missing --cov-report=html
	@echo "Coverage report: htmlcov/index.html"

# ── Docker ─────────────────────────────────────────────────────────────────

docker-build:  ## Build the Docker image
	docker build -t taskforge:latest .

docker-run:    ## Run the app in Docker (port 8000)
	docker run --rm -p 8000:8000 \
	  -e SECRET_KEY=docker-dev-key \
	  -e DATABASE_URL=sqlite:///./taskforge.db \
	  taskforge:latest

# ── Cleanup ────────────────────────────────────────────────────────────────

clean:         ## Remove generated files and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name htmlcov -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name ".coverage" -delete 2>/dev/null || true
	find . -name "*.db" -delete 2>/dev/null || true
