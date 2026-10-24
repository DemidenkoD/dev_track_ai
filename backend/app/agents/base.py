"""Shared google-genai wrapper for DevTrack AI runtime agents.

All runtime agents (project_mentor, rubric_analyst, progress_analyst,
diary_analyst, security_reviewer, oncall_agent) use this module so that:

- Configuration comes from ``GEMINI_API_KEY`` / ``GEMINI_MODEL`` (via
  ``backend/app/core/config.py`` when Track 1 provides it, else env vars).
- Every LLM call enforces Structured Outputs via
  ``types.GenerateContentConfig(response_mime_type="application/json",
  response_schema=...)`` with Pydantic schemas from
  ``backend/app/schemas/agent_outputs.py``.
- Offline / CI / unit-test environments without a key (or on rate-limit /
  transport errors) degrade gracefully to a caller-supplied deterministic
  fallback instead of raising — never breaking ``pytest`` runs.

Safety: this module never prints, logs, or includes secret values
(GEMINI_API_KEY, MAIL_SMTP_PASS, SECRET_KEY) in prompts, logs, or errors.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

# Ensure the `backend/` directory (parent of the `app/` package) is on
# sys.path so `from app.schemas...` works whether this module is imported as
# `app.agents.base` (PYTHONPATH=backend, canonical) or as
# `backend.app.agents.base` (PYTHONPATH=repo root, harness-style).
_BACKEND_DIR = str(Path(__file__).resolve().parents[2])
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

# Import path compat: repo code uses `from app.schemas...` with `backend/`
# on sys.path, while some harnesses import `backend.app...`.
try:  # pragma: no cover - import alias resolution
    from app.core.config import settings as _app_settings  # type: ignore
except Exception:  # Track 1 core may not exist yet (greenfield)
    _app_settings = None


def get_gemini_model() -> str:
    """Return configured Gemini model name with safe default."""
    if _app_settings is not None:
        model = getattr(_app_settings, "GEMINI_MODEL", None)
        if model:
            return str(model)
    return os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)


def get_gemini_api_key() -> str | None:
    """Return GEMINI_API_KEY without ever logging its value."""
    if _app_settings is not None:
        key = getattr(_app_settings, "GEMINI_API_KEY", None)
        if key:
            return str(key)
    return os.environ.get("GEMINI_API_KEY")


def is_gemini_configured() -> bool:
    """True only when a non-placeholder API key is present."""
    key = get_gemini_api_key()
    if not key:
        return False
    lowered = key.strip().lower()
    if lowered in {"", "your_gemini_api_key_here", "change-me", "test", "dummy"}:
        return False
    return True


class GeminiUnavailableError(RuntimeError):
    """Raised when Gemini cannot be called (no key, missing SDK, transport error)."""


def _build_client() -> Any:
    """Build a ``genai.Client`` or raise GeminiUnavailableError (never logs key)."""
    if not is_gemini_configured():
        raise GeminiUnavailableError(
            "GEMINI_API_KEY is not configured; using deterministic fallback."
        )
    try:
        from google import genai  # type: ignore
    except Exception as exc:
        raise GeminiUnavailableError(
            f"google-genai SDK unavailable: {exc}; using deterministic fallback."
        ) from exc
    return genai.Client(api_key=get_gemini_api_key())


def call_gemini_structured(
    *,
    system_instruction: str,
    user_prompt: str,
    response_schema: Any,
    temperature: float = 0.2,
    max_output_tokens: int = 4096,
) -> dict[str, Any]:
    """Call Gemini with enforced JSON structured output; return parsed dict.

    Uses ``types.GenerateContentConfig(response_mime_type="application/json",
    response_schema=...)`` per ``backend/app/agents/AGENTS.md``. Raises
    :class:`GeminiUnavailableError` on missing key/SDK/transport/parse issues
    so callers can fall back deterministically. Never includes secrets.
    """
    client = _build_client()
    try:
        from google.genai import types  # type: ignore
    except Exception as exc:
        raise GeminiUnavailableError(
            f"google.genai.types unavailable: {exc}"
        ) from exc

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=response_schema,
        system_instruction=system_instruction,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )
    try:
        response = client.models.generate_content(
            model=get_gemini_model(),
            contents=user_prompt,
            config=config,
        )
    except Exception as exc:
        # Never include key material; only error class name.
        raise GeminiUnavailableError(
            f"Gemini request failed ({type(exc).__name__}); using fallback."
        ) from exc

    # SDK may already parse into response.parsed when response_schema given.
    parsed = getattr(response, "parsed", None)
    if parsed is not None:
        if hasattr(parsed, "model_dump"):
            return dict(parsed.model_dump())
        if isinstance(parsed, dict):
            return parsed
    text = getattr(response, "text", "") or ""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise GeminiUnavailableError(
            "Gemini returned non-JSON output; using deterministic fallback."
        ) from exc
    if not isinstance(data, dict):
        raise GeminiUnavailableError(
            "Gemini returned non-object JSON; using deterministic fallback."
        )
    return data


T = TypeVar("T")


def run_with_fallback(
    *,
    prompt_builder: Callable[[], tuple[str, str]],
    response_schema: Any,
    parse: Callable[[dict[str, Any]], T],
    fallback: Callable[[Exception | None], T],
    temperature: float = 0.2,
    max_output_tokens: int = 4096,
) -> T:
    """Run a Gemini structured call, degrading to ``fallback`` on any failure.

    ``prompt_builder`` returns ``(system_instruction, user_prompt)``.
    ``parse`` validates the raw dict into the agent's Pydantic output.
    ``fallback`` receives the causing exception (or None) and must return a
    valid schema instance (typically ``needs_review`` / low confidence).
    """
    system_instruction, user_prompt = prompt_builder()
    try:
        raw = call_gemini_structured(
            system_instruction=system_instruction,
            user_prompt=user_prompt,
            response_schema=response_schema,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        return parse(raw)
    except GeminiUnavailableError as exc:
        logger.info("Gemini unavailable (%s); using deterministic fallback.", type(exc).__name__)
        return fallback(exc)
    except Exception as exc:  # validation or unexpected error -> safe fallback
        logger.warning(
            "Agent structured-output parse failed (%s); using fallback.",
            type(exc).__name__,
        )
        return fallback(exc)


ADVISORY_NOTICE = (
    "AI estimates are advisory only and never constitute an official course grade. "
    "ai_proposed_points and ai_reasoning are preserved even after human override."
)
