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
.PHONY: up-prod down-prod logs-prod ps-prod check-prod-env

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

check-prod-env: ## Preflight VPS/local .env: SECRET_KEY/DATABASE_URL present? GLM/ZAI, OPENCODE (OPENCODE_API_KEY alias accepted) or GEMINI key set (auto GLM(direct)>OPENCODE>GEMINI; LLM_PROVIDER=opencode forces opencode.ai inference gateway https://opencode.ai/inference/openai/v1 with OPENCODE_MODEL pass-through; boolean only, values never logged)
	@ENV_FILE="$${ENV_FILE:-.env}"; \
	if [ ! -f "$$ENV_FILE" ]; then echo "ERROR: $$ENV_FILE missing — create it from .env.example on the VPS."; exit 1; fi; \
	if grep -q '^SECRET_KEY=.\+' "$$ENV_FILE"; then echo "SECRET_KEY present (value never logged)."; else echo "ERROR: SECRET_KEY missing or empty in $$ENV_FILE."; exit 1; fi; \
	if grep -q '^DATABASE_URL=.\+' "$$ENV_FILE"; then echo "DATABASE_URL present (value never logged)."; else echo "ERROR: DATABASE_URL missing or empty in $$ENV_FILE."; exit 1; fi; \
	GEMINI_SET=false; OPENCODE_SET=false; OPENCODE_API_KEY_SET=false; GLM_SET=false; ZAI_SET=false; \
	if ! grep -Eq '^GEMINI_API_KEY=(your_gemini_api_key_here|change-me|test|dummy|""|"")?[[:space:]]*$$' "$$ENV_FILE"; then GEMINI_SET=true; fi; \
	if ! grep -Eq '^OPENCODE_KEY=(your_opencode_key_here|your_opencode_api_key_here|change-me|test|dummy|""|"")?[[:space:]]*$$' "$$ENV_FILE"; then OPENCODE_SET=true; fi; \
	if ! grep -Eq '^OPENCODE_API_KEY=(your_opencode_api_key_here|your_opencode_key_here|change-me|test|dummy|""|"")?[[:space:]]*$$' "$$ENV_FILE"; then OPENCODE_API_KEY_SET=true; fi; \
	if ! grep -Eq '^GLM_API_KEY=(your_glm_key_here|change-me|test|dummy|""|"")?[[:space:]]*$$' "$$ENV_FILE"; then GLM_SET=true; fi; \
	if ! grep -Eq '^ZAI_API_KEY=(change-me|test|dummy|""|"")?[[:space:]]*$$' "$$ENV_FILE"; then ZAI_SET=true; fi; \
	echo "GEMINI_API_KEY_SET=$$GEMINI_SET (boolean only, content not shown)."; \
	echo "OPENCODE_API_KEY_SET=$$OPENCODE_API_KEY_SET (boolean only, content not shown)."; \
	echo "OPENCODE_KEY_SET=$$OPENCODE_SET (boolean only, content not shown)."; \
	echo "GLM_API_KEY_SET=$$GLM_SET (boolean only, content not shown)."; \
	echo "ZAI_API_KEY_SET=$$ZAI_SET (boolean only, content not shown)."; \
	if [ "$$GLM_SET" = "true" ] || [ "$$ZAI_SET" = "true" ]; then echo "EFFECTIVE_LLM_PROVIDER=glm (auto GLM(direct)>OPENCODE>GEMINI, LLM_PROVIDER=auto; LLM_PROVIDER=opencode forces gateway for GLM-via-opencode; explicit LLM_PROVIDER=glm|opencode|gemini overrides auto)."; \
	elif [ "$$OPENCODE_SET" = "true" ] || [ "$$OPENCODE_API_KEY_SET" = "true" ]; then echo "EFFECTIVE_LLM_PROVIDER=opencode (auto GLM(direct)>OPENCODE>GEMINI, LLM_PROVIDER=auto; LLM_PROVIDER=opencode forces gateway for GLM-via-opencode even if GLM_* keys present; explicit LLM_PROVIDER=glm|opencode|gemini overrides auto). IF OPENCODE_API_KEY or OPENCODE_KEY (either) present takes precedence per LLM_PROVIDER."; \
	elif [ "$$GEMINI_SET" = "true" ]; then echo "EFFECTIVE_LLM_PROVIDER=gemini (auto GLM(direct)>OPENCODE>GEMINI, LLM_PROVIDER=auto; LLM_PROVIDER=opencode forces gateway for GLM-via-opencode; explicit LLM_PROVIDER=glm|opencode|gemini overrides auto)."; \
	else echo "WARNING: GEMINI_API_KEY_SET=false, OPENCODE_API_KEY_SET=false, OPENCODE_KEY_SET=false, GLM_API_KEY_SET=false and ZAI_API_KEY_SET=false (missing or .env.example placeholder) — backend/worker will boot DEGRADED with deterministic fallback (zero LLM usage, health stays green). Set any one key. Precedence when LLM_PROVIDER=auto: GLM(direct)>OPENCODE>GEMINI; LLM_PROVIDER=opencode forces gateway (for GLM-via-opencode) at https://opencode.ai/inference/openai/v1. See infra/RUNBOOK_GEMINI_VPS.md."; fi

test-backend: ## Run backend pytest inside a throwaway container (Track 5 owns test content; tests/ bind-mounted because the image excludes them)
	$(COMPOSE) -f $(DEV_FILE) run --rm -v ./backend/tests:/code/tests:ro backend python -m pytest -q

clean: ## Stop stack AND delete named volumes (destructive: drops local DB + telemetry data)
	$(COMPOSE) -f $(DEV_FILE) down -v
