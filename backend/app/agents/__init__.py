"""DevTrack AI runtime Gemini agents (Track 2).

Layer A agents per ``docs/specs/AGENT_TEAM_SPEC.md``. All are advisory and
read-only: they never push commits, open PRs, or mutate user repositories,
and AI point estimates are never presented as official course grades.

Single source for the advisory disclaimer: :data:`ADVISORY_NOTICE` in
``app.agents.base``. (Track 3's ``app.services.analysis_pipeline`` carries a
local copy for import-safety; Track 2 never duplicates the string elsewhere.)
"""

from __future__ import annotations

from app.agents import (
    diary_analyst,
    oncall_agent,
    progress_analyst,
    project_mentor,
    rubric_analyst,
    security_reviewer,
)
from app.agents.base import (
    ADVISORY_NOTICE,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GLM_BASE_URL,
    DEFAULT_GLM_MODEL,
    DEFAULT_OPENCODE_BASE_URL,
    DEFAULT_OPENCODE_MODEL,
    GLM_TOP_P,
    GLM_TEMPERATURE,
    GeminiUnavailableError,
    call_gemini_structured,
    call_llm_structured,
    get_effective_llm_api_key,
    get_effective_llm_model,
    get_effective_llm_provider,
    get_gemini_api_key,
    get_gemini_model,
    get_glm_api_key,
    get_glm_base_url,
    get_glm_model,
    get_llm_provider,
    get_opencode_api_key,
    get_opencode_base_url,
    get_opencode_model,
    is_gemini_configured,
    is_glm_configured,
    is_opencode_configured,
    is_opencode_openai_mode,
    run_with_fallback,
)

__all__ = [
    "ADVISORY_NOTICE",
    "DEFAULT_GEMINI_MODEL",
    "DEFAULT_GLM_BASE_URL",
    "DEFAULT_GLM_MODEL",
    "DEFAULT_OPENCODE_BASE_URL",
    "DEFAULT_OPENCODE_MODEL",
    "GLM_TOP_P",
    "GLM_TEMPERATURE",
    "GeminiUnavailableError",
    "call_gemini_structured",
    "call_llm_structured",
    "diary_analyst",
    "get_effective_llm_api_key",
    "get_effective_llm_model",
    "get_effective_llm_provider",
    "get_gemini_api_key",
    "get_gemini_model",
    "get_glm_api_key",
    "get_glm_base_url",
    "get_glm_model",
    "get_llm_provider",
    "get_opencode_api_key",
    "get_opencode_base_url",
    "get_opencode_model",
    "is_gemini_configured",
    "is_glm_configured",
    "is_opencode_configured",
    "is_opencode_openai_mode",
    "oncall_agent",
    "progress_analyst",
    "project_mentor",
    "rubric_analyst",
    "run_with_fallback",
    "security_reviewer",
]
