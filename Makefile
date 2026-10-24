# DevTrack AI — Track 6 convenience targets (docker compose wrappers only).
# No application logic here; Track 1-5 own their test/typecheck commands.
COMPOSE ?= docker compose
DEV_FILE ?= docker-compose.yml
PROD_FILE ?= docker-compose.prod.yml

.PHONY: up down build logs ps config config-prod test-backend clean

up: ## Start local stack (single command): db + backend + worker + frontend + observability
	$(COMPOSE) -f $(DEV_FILE) up --build -d
	$(COMPOSE) -f $(DEV_FILE) ps

down: ## Stop local stack (keep volumes)
	$(COMPOSE) -f $(DEV_FILE) down

build: ## Build backend/worker/frontend images
	$(COMPOSE) -f $(DEV_FILE) build backend worker frontend

logs: ## Tail all service logs (or SERVICE=name for one service)
	$(COMPOSE) -f $(DEV_FILE) logs -f $(SERVICE)

ps: ## Show stack status
	$(COMPOSE) -f $(DEV_FILE) ps

config: ## Validate local compose file
	$(COMPOSE) -f $(DEV_FILE) config --quiet && echo "docker-compose.yml OK"

config-prod: ## Validate production compose file
	$(COMPOSE) -f $(PROD_FILE) config --quiet && echo "docker-compose.prod.yml OK"

test-backend: ## Run backend pytest inside a throwaway container (Track 5 owns test content)
	$(COMPOSE) -f $(DEV_FILE) run --rm backend python -m pytest -q

clean: ## Stop stack AND delete named volumes (destructive: drops local DB + telemetry data)
	$(COMPOSE) -f $(DEV_FILE) down -v
