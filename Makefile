APP_ENV ?= dev
export APP_ENV

BACKEND  := cd backend &&
FRONTEND := cd frontend &&

.PHONY: help setup run dev-web test lint typecheck build-web check provision provision-check register-desktop demo-transcript

help:  ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

setup:  ## Install backend and frontend dependencies
	$(BACKEND) uv sync
	$(FRONTEND) npm ci

run:  ## Start the API for APP_ENV (default dev) on its api_url port (dev 8000, staging 8001, prod 8002)
	$(BACKEND) uv run meridian serve --reload

# The API address for APP_ENV, read from environments/<env>.yaml (evaluated only when used).
API_URL ?= $(shell cd backend && uv run -q python -c "from app.core.config import Settings; from app.core.env_config import load_policy; print(load_policy(Settings()).api_url)")

dev-web:  ## Start the admin console on :5173, proxying /api to APP_ENV's API
	$(FRONTEND) API_URL=$(API_URL) npm run dev

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

provision:  ## Render + validate permissions manifest and Claude host config for dev, staging, prod
	$(BACKEND) uv run meridian provision

provision-check:  ## Fail if committed config differs from what the inputs render (CI)
	$(BACKEND) uv run meridian provision --check

SOURCE ?= release
register-desktop:  ## Add the connector to Claude Desktop: make register-desktop ENV=prod AS=<user_id> [SOURCE=local]
	@test -n "$(ENV)" -a -n "$(AS)" || { echo "usage: make register-desktop ENV=<dev|staging|prod> AS=<user_id> [SOURCE=local]"; exit 2; }
	$(BACKEND) uv run meridian register-desktop --env $(ENV) --user $(AS) --source $(SOURCE)

demo-transcript:  ## Regenerate docs/demo/transcript.md: the connector over stdio against a fresh prod service
	$(BACKEND) uv run python -m app.connector.demo

check: lint typecheck test build-web provision-check  ## Everything CI runs
