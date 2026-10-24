# DevTrack AI — Track 6 convenience targets (docker compose wrappers only).
# No application logic here; Track 1-5 own their test/typecheck commands.
#
# Loki log-shipping example (OPT-IN, not part of `make up`):
#   The backend/worker `logging:` stanzas in docker-compose*.yml stay commented
#   until the host has the loki docker plugin. To enable log shipping:
#     docker plugin install grafana/loki-docker-driver:latest --alias loki --grant-all-permissions
#   then uncomment the `logging:` blocks (labels {app="backend"}/{app="worker"},
#   OTEL traces already point at OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4317).
COMPOSE ?= docker compose
DEV_FILE ?= docker-compose.yml
PROD_FILE ?= docker-compose.prod.yml
# Dummy values ONLY so `config-prod`/CI can validate the prod file, whose
# :? guards must fail fast at real deploy time (never used to run anything).
PROD_CONFIG_ENV ?= POSTGRES_PASSWORD=dummy-validation-only DATABASE_URL=postgresql+psycopg://dummy:dummy@db:5432/dummy SECRET_KEY=dummy-validation-only GF_SECURITY_ADMIN_PASSWORD=dummy-validation-only

.PHONY: up down build logs ps config config-prod test-backend clean
.PHONY: up-prod down-prod logs-prod ps-prod

up: ## Start local stack (single command): db + backend + worker + frontend + observability
	$(COMPOSE) -f $(DEV_FILE) up --build -d
	$(COMPOSE) -f $(DEV_FILE) ps

down: ## Stop local stack (keep volumes)
	$(COMPOSE) -f $(DEV_FILE) down

up-prod: ## Start production stack (requires real .env with POSTGRES_PASSWORD/DATABASE_URL/SECRET_KEY/GF_SECURITY_ADMIN_PASSWORD)
	$(COMPOSE) -f $(PROD_FILE) up --build -d
	$(COMPOSE) -f $(PROD_FILE) ps

down-prod: ## Stop production stack (keep volumes)
	$(COMPOSE) -f $(PROD_FILE) down

build: ## Build backend/worker/frontend images
	$(COMPOSE) -f $(DEV_FILE) build backend worker frontend

logs: ## Tail all service logs (or SERVICE=name for one service)
	$(COMPOSE) -f $(DEV_FILE) logs -f $(SERVICE)

logs-prod: ## Tail production service logs (or SERVICE=name for one service)
	$(COMPOSE) -f $(PROD_FILE) logs -f $(SERVICE)

ps: ## Show stack status
	$(COMPOSE) -f $(DEV_FILE) ps

ps-prod: ## Show production stack status
	$(COMPOSE) -f $(PROD_FILE) ps

config: ## Validate local compose file
	$(COMPOSE) -f $(DEV_FILE) config --quiet && echo "docker-compose.yml OK"

config-prod: ## Validate production compose file (dummy secrets satisfy :? guards for validation only)
	$(PROD_CONFIG_ENV) $(COMPOSE) -f $(PROD_FILE) config --quiet && echo "docker-compose.prod.yml OK"

test-backend: ## Run backend pytest inside a throwaway container (Track 5 owns test content; tests/ bind-mounted because the image excludes them)
	$(COMPOSE) -f $(DEV_FILE) run --rm -v ./backend/tests:/code/tests:ro backend python -m pytest -q

clean: ## Stop stack AND delete named volumes (destructive: drops local DB + telemetry data)
	$(COMPOSE) -f $(DEV_FILE) down -v
