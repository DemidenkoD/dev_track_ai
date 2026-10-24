# Runtime AI Agents Rules (`backend/app/agents/AGENTS.md`)

These rules govern the implementation of DevTrack AI's specialized Gemini agents inside `backend/app/agents/`.

## 1. Official Gemini SDK & Configuration
- Always use the `google-genai` SDK (`from google import genai` and `from google.genai import types`).
- Read `GEMINI_API_KEY` and `GEMINI_MODEL` (default fallback `gemini-2.5-flash`) from `backend/app/core/config.py`.
- Enforce **Structured Outputs** on every LLM call using `types.GenerateContentConfig(response_mime_type="application/json", response_schema=...)` with Pydantic schemas defined in `backend/app/schemas/agent_outputs.py`.
- Provide a deterministic fallback / graceful degradation mode when `GEMINI_API_KEY` is unavailable or rate-limited during unit/CI testing.

## 2. Mandatory Agent Grounding & Evidence Rules
1. **No Invented Scoring Rules:** The `RubricAnalyst` agent must evaluate each criterion strictly against the official `scoring_levels` JSON loaded from `docs/rubrics/ai_dev_tools_zoomcamp_2026.json` (or the active versioned rubric in the DB).
2. **Mandatory Evidence Citations:** Every score or recommendation must reference concrete `evidence_ids` or repository file paths/commit SHAs inspected during the run.
3. **Explicit Uncertainty & `needs_review` State:** When repository evidence is ambiguous, incomplete, or cannot be verified statically (e.g., runtime cloud behavior without reachable deployment URL), the agent must set `score_state="needs_review"` and lower `ai_confidence` (< 0.70) rather than guessing.
4. **Secret Redaction Before Prompting:** Never include raw secret values from Gitleaks or `.env` files inside prompts sent to Gemini. Only send rule IDs, file paths, line numbers, and redacted snippets.
5. **Bounded Read-Only On-Call Agent:** `oncall_agent.py` may only read metrics, logs, traces, and alert payloads. It has zero shell execution or database mutation tools.

