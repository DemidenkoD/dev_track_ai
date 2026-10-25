# Runbook: Zero Gemini Usage on VPS (Placeholder / Empty `GEMINI_API_KEY`)

**Symptom:** production app looks healthy (`/api/v1/health` returns `ok`),
but the Google AI dashboard shows **zero Gemini usage** and analyses look
generic/deterministic.

**Root cause:** the VPS `.env` still carries the `.env.example` placeholder
(`GEMINI_API_KEY=your_gemini_api_key_here`) or an empty value. Compose
wiring (`docker-compose.prod.yml`, `backend` + `worker` services) injects
`GEMINI_API_KEY` **only** via compose `environment:` — intentionally with
**no `:?` guard** so the stack boots **degraded** instead of crash-looping.
`is_gemini_configured()` (`backend/app/agents/base.py`) returns `False` for
empty/placeholder keys, and every agent silently uses its deterministic
fallback. (Also note: `backend/Dockerfile` `WORKDIR` is `/code`, so pydantic
`env_file=".env"` would look at `/code/.env`, which is absent from the image
— only the compose injection path matters.)

> **Secret safety:** every command below reports **boolean / length / count
> only**. Never `cat` the `.env`, never `echo $GEMINI_API_KEY`, never
> `printenv | grep GEMINI` (that prints the value). No real key ever belongs
> in this repo, in logs, or in traces.

## 1. Diagnose (on the VPS, values never printed)

```bash
cd "$VPS_FOLDER"   # e.g. cd /srv/devtrack-ai — your VPS_FOLDER value

# Is the line present at all? (count only — safe to read in logs)
grep -c '^GEMINI_API_KEY=.\+' .env || true

# Is it the placeholder / empty / dummy? (boolean only)
grep -E '^GEMINI_API_KEY=(your_gemini_api_key_here|change-me|test|dummy|""|"")?[[:space:]]*$' .env \
  && echo 'GEMINI_API_KEY_SET=false (placeholder or empty — deterministic fallback active)' \
  || echo 'GEMINI_API_KEY_SET=true (non-placeholder value present, content not shown)'

# Same check inside the RUNNING containers (count only — never prints values):
docker compose -f docker-compose.prod.yml exec -T backend sh -c 'env | grep -c GEMINI'
docker compose -f docker-compose.prod.yml exec -T worker  sh -c 'env | grep -c GEMINI'
# Expect 2/2 lines each (KEY + MODEL names). A count of 1 means MODEL only.
```

Or from your laptop (no secrets cross the wire beyond SSH):

```bash
make check-prod-env ENV_FILE=.env   # boolean-only report, see Makefile
```

The deploy workflow (`deploy-vps.yml`) also emits a visible `::warning::`
with the same boolean verdict on every deploy — check the deploy logs first.

## 2. Fix (on the VPS)

```bash
cd "$VPS_FOLDER"   # e.g. cd /srv/devtrack-ai

# Edit ONLY the GEMINI_API_KEY line (paste the real key from Google AI Studio;
# nothing else in .env is touched by these steps):
nano .env

# Re-verify without revealing the key (boolean only):
grep -E '^GEMINI_API_KEY=(your_gemini_api_key_here|change-me|test|dummy|""|"")?[[:space:]]*$' .env \
  && echo 'STILL PLACEHOLDER — fix .env first' \
  || echo 'GEMINI_API_KEY_SET=true'

# Recreate backend + worker so the new env is injected:
docker compose -f docker-compose.prod.yml up -d backend worker

# Confirm injection reached the containers (counts only):
docker compose -f docker-compose.prod.yml exec -T backend sh -c 'if [ -z "$GEMINI_API_KEY" ]; then echo GEMINI_API_KEY_SET=false; else echo GEMINI_API_KEY_SET=true; fi'
docker compose -f docker-compose.prod.yml exec -T worker  sh -c 'if [ -z "$GEMINI_API_KEY" ]; then echo GEMINI_API_KEY_SET=false; else echo GEMINI_API_KEY_SET=true; fi'

# Health stays green either way (health does NOT expose the key):
curl -fsS https://ct-academia.pl/api/v1/health
```

## 3. Confirm live Gemini (not fallback)

1. Trigger one manual analysis from the UI (or `POST /api/v1/projects/{id}/analyses`).
2. Google AI dashboard should show new requests within minutes.
3. If usage is still zero after a `GEMINI_API_KEY_SET=true` restart, check
   container logs for `GeminiUnavailableError` / transport errors (SDK or
   egress issue, not a placeholder issue):
   `docker compose -f docker-compose.prod.yml logs --tail=100 worker`

## Why the deploy never fixes this for you

`deploy-vps.yml` deliberately **never overwrites** VPS `.env` (only
auto-fills `GF_SECURITY_ADMIN_PASSWORD` once and replaces the dev
`SECRET_KEY` placeholder). `git pull --ff-only` never touches untracked
files, and there is no `git reset --hard` / `clean`. So a placeholder key
survives every deploy — the `::warning::` in the deploy log is the signal,
this runbook is the fix.
