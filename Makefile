.PHONY: dev build test clean logs backend-test frontend-lint cli-test

# ==============================================================================
# Development
# ==============================================================================

## Start all services in development mode
dev:
	docker compose up --build

## Start services in background
dev-bg:
	docker compose up --build -d

## Stop all services
stop:
	docker compose down

## View logs
logs:
	docker compose logs -f

## View backend logs only
logs-backend:
	docker compose logs -f backend

# ==============================================================================
# Testing
# ==============================================================================

## Run all tests
test: backend-test cli-test

## Run backend tests
backend-test:
	cd backend && python -m pytest tests/ -v --tb=short

## Run backend tests with coverage
backend-cov:
	cd backend && python -m pytest tests/ -v --cov=. --cov-report=term-missing

## Run CLI tests
cli-test:
	cd cli && python -m pytest tests/ -v --tb=short

## Run frontend lint
frontend-lint:
	cd frontend && npm run lint

## Run frontend build check
frontend-build:
	cd frontend && npm run build

# ==============================================================================
# Build
# ==============================================================================

## Build all Docker images
build:
	docker compose build

## Build backend image only
build-backend:
	docker compose build backend

## Build frontend image only
build-frontend:
	docker compose build frontend

# ==============================================================================
# Cleanup
# ==============================================================================

## Remove all containers and volumes
clean:
	docker compose down -v --remove-orphans
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .next -exec rm -rf {} + 2>/dev/null || true

## Remove Docker images
clean-images:
	docker compose down -v --rmi all --remove-orphans

# ==============================================================================
# Database
# ==============================================================================

## Initialize database tables
db-init:
	docker compose exec backend python -c "from database import init_db; init_db()"

## Open psql shell
db-shell:
	docker compose exec postgres psql -U llmlab -d llmlab

# ==============================================================================
# Help
# ==============================================================================

## Show this help
help:
	@echo "LLMLab Development Commands"
	@echo "==========================="
	@echo ""
	@echo "  make dev            Start all services"
	@echo "  make dev-bg         Start services in background"
	@echo "  make stop           Stop all services"
	@echo "  make test           Run all tests"
	@echo "  make backend-test   Run backend tests"
	@echo "  make backend-cov    Run backend tests with coverage"
	@echo "  make build          Build all Docker images"
	@echo "  make clean          Remove containers and volumes"
	@echo "  make logs           View all logs"
	@echo "  make db-init        Initialize database tables"
	@echo "  make db-shell       Open PostgreSQL shell"
	@echo ""
