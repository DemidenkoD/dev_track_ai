"""DevTrack AI runtime Gemini agents (Track 2).

Layer A agents per ``docs/specs/AGENT_TEAM_SPEC.md``. All are advisory and
read-only: they never push commits, open PRs, or mutate user repositories,
and AI point estimates are never presented as official course grades.
"""

try:
    from app.agents.base import (
        ADVISORY_NOTICE,
        DEFAULT_GEMINI_MODEL,
        GeminiUnavailableError,
        call_gemini_structured,
        get_gemini_api_key,
        get_gemini_model,
        is_gemini_configured,
        run_with_fallback,
    )
except ImportError:  # harness imports as backend.app.*: fix sys.path first
    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
    from app.agents.base import (
        ADVISORY_NOTICE,
        DEFAULT_GEMINI_MODEL,
        GeminiUnavailableError,
        call_gemini_structured,
        get_gemini_api_key,
        get_gemini_model,
        is_gemini_configured,
        run_with_fallback,
    )

__all__ = [
    "ADVISORY_NOTICE",
    "DEFAULT_GEMINI_MODEL",
    "GeminiUnavailableError",
    "call_gemini_structured",
    "get_gemini_api_key",
    "get_gemini_model",
    "is_gemini_configured",
    "run_with_fallback",
]
