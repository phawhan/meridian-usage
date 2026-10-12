APP_ENV ?= dev
export APP_ENV

BACKEND  := cd backend &&
FRONTEND := cd frontend &&

.PHONY: help setup run dev-web test lint typecheck build-web check

help:  ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

setup:  ## Install backend and frontend dependencies
	$(BACKEND) uv sync
	$(FRONTEND) npm ci

run:  ## Start the API for APP_ENV (default dev) on :8000
	$(BACKEND) uv run uvicorn app.main:app --reload --port 8000

dev-web:  ## Start the admin console on :5173 (proxies /api to :8000)
	$(FRONTEND) npm run dev

test:  ## Run backend tests
	$(BACKEND) uv run pytest

lint:  ## Lint backend and frontend
	$(BACKEND) uv run ruff check .
	$(BACKEND) uv run ruff format --check .
	$(FRONTEND) npm run lint

typecheck:  ## Type-check backend (mypy strict) and frontend (tsc)
	$(BACKEND) uv run mypy app tests
	$(FRONTEND) npm run typecheck

build-web:  ## Production build of the admin console
	$(FRONTEND) npm run build

check: lint typecheck test build-web  ## Everything CI runs
