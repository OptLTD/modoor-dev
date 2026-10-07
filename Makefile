.PHONY: help setup db build dev preview mcp web webui api test smoke external base wiki sale skill doc fleet freight capacity dispatch sync flow worker seed

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PYTHON := $(ROOT)/.venv/bin/python
PIP := $(PYTHON) -m pip
VENV := $(ROOT)/.venv

# Extra goals after command → module ids
DEV_MODULES := $(filter-out dev setup db worker seed,$(MAKECMDGOALS))
BUILD_MODULES := $(filter-out build setup,$(MAKECMDGOALS))
PREVIEW_MODULES := $(filter-out preview setup,$(MAKECMDGOALS))
SEED_MODULES := $(filter-out seed setup force,$(MAKECMDGOALS))

# set BUILD=1 with preview to compile first: make preview BUILD=1 [modules]
BUILD ?= 0
# set FORCE_SETUP=1 to re-run pip install even if stamp is fresh
FORCE_SETUP ?= 0
export PIP_DISABLE_PIP_VERSION_CHECK := 1

help: ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'
	@echo ""
	@echo "  make db                      # 可选：没有本机 Postgres 时才用 compose 起一份"
	@echo "  make worker                  # job queue (optional; API 默认带进程内 worker)"
	@echo "  make seed                    # 手动写入 demo（sale/fleet/dispatch）"
	@echo "  make seed fleet              # 只 seed 车队；可加 FORCE=1"
	@echo "  make seed city FORCE=1       # 北京城配订单/站点/车辆"
	@echo "  make build base wiki"
	@echo "  make preview                 # mount dist on API (no vite)"
	@echo "  make preview base"
	@echo "  make preview BUILD=1         # build then preview (all)"
	@echo "  make preview BUILD=1 base    # build then preview base"
	@echo "  make dev base                # HMR via :8765 proxy"

setup: ## Create venv and install package (skips pip if up to date)
	@test -d "$(VENV)" || python3 -m venv "$(VENV)"
	@stamp="$(VENV)/.modoor-setup-stamp"; \
	need=0; \
	if [ "$(FORCE_SETUP)" = "1" ]; then need=1; \
	elif [ ! -f "$$stamp" ]; then need=1; \
	elif [ "$(ROOT)/pyproject.toml" -nt "$$stamp" ]; then need=1; \
	fi; \
	if [ "$$need" = "1" ]; then \
		echo ">> pip install -e .[dev]"; \
		$(PIP) install --disable-pip-version-check -q -e ".[dev]"; \
		touch "$$stamp"; \
	fi
	@test -f .env || cp .env.example .env
	@echo "setup ok"

db: ## Optional: start Compose Postgres if you do not already have one
	docker compose up -d --wait db
	@echo "Only needed when DATABASE_URL does not already point at a running Postgres."

build: setup ## Build module dist: make build base [wiki] [sale] [skill]
	@if [ -z "$(BUILD_MODULES)" ]; then \
		echo "usage: make build <module> [module...]"; \
		echo "  modules: base wiki sale skill doc fleet freight capacity dispatch flow"; \
		echo "  (sync is tools-only — no vite webui)"; \
		echo "  example: make build base"; \
		echo "           make build base wiki"; \
		exit 1; \
	fi
	@chmod +x "$(ROOT)/scripts/run_build.sh"
	@"$(ROOT)/scripts/run_build.sh" $(BUILD_MODULES)

dev: setup ## Start API + vite HMR: make dev base [wiki] [sale] [skill]
	@if [ -z "$(DEV_MODULES)" ]; then \
		echo "usage: make dev <module> [module...]"; \
		echo "  modules: base wiki sale skill doc fleet freight capacity dispatch flow"; \
		echo "  (sync is tools-only — no vite webui)"; \
		echo "  example: make dev base"; \
		echo "           make dev base wiki"; \
		exit 1; \
	fi
	@$(PYTHON) scripts/ensure_db.py
	@chmod +x "$(ROOT)/scripts/run_dev.sh"
	@exec "$(ROOT)/scripts/run_dev.sh" $(DEV_MODULES)

preview: setup ## Preview dist (no build): make preview [modules]; BUILD=1 to rebuild
	@$(PYTHON) scripts/ensure_db.py
	@chmod +x "$(ROOT)/scripts/run_preview.sh"
	@BUILD="$(BUILD)" exec "$(ROOT)/scripts/run_preview.sh" $(PREVIEW_MODULES)

# Swallow module names used as: make build|dev|preview|seed base wiki …
base wiki sale skill doc fleet freight capacity dispatch sync flow city force:
	@:

web: ## Alias: make web base … → make dev …
	@$(MAKE) dev $(filter-out web,$(MAKECMDGOALS))

webui: ## Module Vue only: make webui base wiki
	@mods="$(filter-out webui,$(MAKECMDGOALS))"; \
	if [ -z "$$mods" ]; then echo "usage: make webui <module> [module...]"; exit 1; fi; \
	for m in $$mods; do \
		d="$(ROOT)/addon/$$m/webui"; \
		if [ ! -d "$$d" ]; then d="$(ROOT)/builtin/$$m/webui"; fi; \
		if [ ! -d "$$d" ]; then echo "missing addon|builtin/$$m/webui"; exit 1; fi; \
		( cd "$$d" && if [ ! -d node_modules ]; then npm install; fi && npm run dev ) & \
	done; wait

api: setup ## API only (:8765)
	@$(PYTHON) scripts/ensure_db.py
	@set -a && source .env && set +a && exec $(PYTHON) -m modoor.web.app

seed: setup ## Seed demo data: make seed [sale|fleet|dispatch|city] FORCE=1
	@$(PYTHON) scripts/ensure_db.py
	@set -a && source .env && set +a; \
	args="$(SEED_MODULES)"; \
	if [ "$(FORCE)" = "1" ]; then args="$$args --force"; fi; \
	$(PYTHON) scripts/seed_demo.py $$args

external: setup ## Start external Board+Pulse (Modoor registry must be up)
	@set -a && source .env && set +a && \
		MODOOR_URL="$${MODOOR_WEBUI_URL:-http://127.0.0.1:8765}" \
		PYTHONPATH="$(ROOT)" $(PYTHON) scripts/run_external_demos.py

mcp: setup ## Run MCP server (stdio; loads .env)
	@set -a && source .env && set +a && exec $(PYTHON) -m modoor.runtime.mcp_server

worker: setup ## Run job worker (doc extract queue)
	@$(PYTHON) scripts/ensure_db.py
	@set -a && source .env && set +a && exec $(PYTHON) -m modoor.runtime.worker

test: setup ## Run pytest (needs Postgres on DATABASE_URL)
	@$(PYTHON) -m pytest -q

smoke: setup ## Run sale smoke flow
	@$(PYTHON) addon/sale/tests/smoke_sale_flow.py
