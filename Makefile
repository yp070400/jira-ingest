.PHONY: up down build restart logs shell migrate seed test lint fmt clean help

# ─── Docker ────────────────────────────────────────────────────────────────
up:
	@echo "Starting JIRA Resolution Intelligence Tool..."
	docker compose up -d --build
	@echo "Waiting for services to be healthy..."
	@sleep 5
	$(MAKE) migrate
	@echo ""
	@echo "✓ Services running:"
	@echo "  Backend:    http://localhost:8000"
	@echo "  API Docs:   http://localhost:8000/docs"
	@echo "  Metrics:    http://localhost:8000/metrics"
	@echo "  Prometheus: http://localhost:9090"

down:
	docker compose down

build:
	docker compose build --no-cache

restart:
	docker compose restart backend

logs:
	docker compose logs -f backend

logs-all:
	docker compose logs -f

shell:
	docker compose exec backend bash

ps:
	docker compose ps

# ─── Database ──────────────────────────────────────────────────────────────
migrate:
	@echo "Running database migrations..."
	docker compose exec backend alembic upgrade head
	@echo "✓ Migrations complete"

migrate-down:
	docker compose exec backend alembic downgrade -1

migrate-create:
	@read -p "Migration name: " name; \
	docker compose exec backend alembic revision --autogenerate -m "$$name"

seed:
	@echo "Seeding database with test data..."
	docker compose exec backend python scripts/seed.py
	@echo "✓ Seed complete"

# ─── Testing ───────────────────────────────────────────────────────────────
test:
	docker compose exec backend pytest tests/ -v --cov=app --cov-report=term-missing

test-unit:
	docker compose exec backend pytest tests/unit/ -v

test-integration:
	docker compose exec backend pytest tests/integration/ -v

test-fast:
	docker compose exec backend pytest tests/ -v -x --tb=short

# ─── Code Quality ──────────────────────────────────────────────────────────
lint:
	docker compose exec backend ruff check app/ tests/

fmt:
	docker compose exec backend ruff format app/ tests/

typecheck:
	docker compose exec backend mypy app/

# ─── Development ───────────────────────────────────────────────────────────
dev:
	@echo "Starting in development mode with hot-reload..."
	docker compose up -d postgres redis
	@sleep 3
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --env-file .env.dev

install:
	pip install -r requirements.txt

# ─── Cleanup ───────────────────────────────────────────────────────────────
clean:
	docker compose down -v --remove-orphans
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true

clean-data:
	@echo "WARNING: This will delete all persistent data (postgres, redis, faiss)!"
	@read -p "Are you sure? [y/N] " confirm; \
	if [ "$$confirm" = "y" ]; then \
		docker compose down -v; \
		echo "✓ Data volumes removed"; \
	fi

# ─── Help ──────────────────────────────────────────────────────────────────
help:
	@echo "JIRA Resolution Intelligence Tool — Makefile Commands"
	@echo ""
	@echo "  make up              Start all services (build + migrate + seed)"
	@echo "  make down            Stop all services"
	@echo "  make build           Rebuild Docker images"
	@echo "  make restart         Restart backend container"
	@echo "  make logs            Tail backend logs"
	@echo "  make logs-all        Tail all service logs"
	@echo "  make shell           Open shell in backend container"
	@echo ""
	@echo "  make migrate         Run Alembic migrations"
	@echo "  make migrate-down    Roll back one migration"
	@echo "  make migrate-create  Create a new migration"
	@echo "  make seed            Seed database with test data"
	@echo ""
	@echo "  make test            Run full test suite"
	@echo "  make test-unit       Run unit tests only"
	@echo "  make test-integration Run integration tests only"
	@echo ""
	@echo "  make lint            Run ruff linter"
	@echo "  make fmt             Format code with ruff"
	@echo ""
	@echo "  make dev             Run with hot-reload (local python)"
	@echo "  make clean           Remove build artifacts"
	@echo "  make clean-data      Remove all persistent volumes"