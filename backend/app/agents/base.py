"""Shared LLM wrapper for DevTrack AI runtime agents (GLM > OPENCODE > GEMINI).

All runtime agents (project_mentor, rubric_analyst, progress_analyst,
diary_analyst, security_reviewer, oncall_agent) use this module so that:

- Configuration comes from ``GLM_API_KEY`` (alias ``ZAI_API_KEY``) /
  ``GLM_MODEL`` / ``GLM_BASE_URL``, else ``OPENCODE_API_KEY`` (alias
  ``OPENCODE_KEY``) / ``OPENCODE_MODEL`` / ``OPENCODE_BASE_URL``, else
  ``GEMINI_API_KEY`` / ``GEMINI_MODEL`` (via
  ``backend/app/core/config.py`` when Track 1 provides it, else env vars).
  ``LLM_PROVIDER`` (``auto`` | ``glm`` | ``opencode`` | ``gemini``) forces
  an explicit provider; ``auto`` (default) uses GLM > OPENCODE > GEMINI
  order. Default models are ``glm-5.3-flash`` for the GLM provider,
  ``muse-spark-1.3-contributor`` for the OpenCode provider and
  ``gemma-4-31b-it`` for Gemini (Gemma 4 31B-IT via the Gemini API using
  the same ``google-genai`` SDK) chosen to avoid Gemini 2.5 Flash RPD/RPM
  rate limits while keeping ``generateContent`` structured-output
  compatibility. ``OPENCODE_MODEL`` is sent **verbatim** to the gateway
  (``opencode-go/`` / ``z-ai/`` prefixes never stripped); accepted forms:
  ``muse-spark-1.3-contributor``, ``kimi-k2.6``, ``glm-5.3-flash``,
  ``opencode-go/glm-5.3-flash``. The opencode provider targets the
  OpenAI-compatible inference endpoint
  (``DEFAULT_OPENCODE_BASE_URL`` =
  ``https://opencode.ai/inference/openai/v1``) via
  ``OpenAI(api_key, base_url)`` and ``chat.completions.create`` with the
  model string passed verbatim; only a legacy custom ``OPENCODE_BASE_URL``
  that is *not* OpenAI-compatible (no ``"/v1"`` /
  ``"opencode.ai/inference"`` marker) keeps the ``genai.Client``
  path.
- Every Gemini/OpenCode LLM call enforces Structured Outputs via
  ``types.GenerateContentConfig(response_mime_type="application/json",
  response_schema=...)`` with Pydantic schemas from
  ``backend/app/schemas/agent_outputs.py``. Gemma 4-IT supports
  ``generateContent`` via the Gemini API with the same config shape.
  GLM calls go through the OpenAI-compatible Zhipu endpoint
  (``https://api.z.ai/api/paas/v4/``) via the ``openai`` SDK with
  ``response_format={"type": "json_object"}`` when supported (plain
  prompt + fence-strip parse otherwise), using the GLM-recommended
  ``temperature=1.0`` / ``top_p=0.95`` (vs ``0.2`` for Gemini/OpenCode).
- Offline / CI / unit-test environments without a key (or on rate-limit /
  transport errors) degrade gracefully to a caller-supplied deterministic
  fallback instead of raising — never breaking ``pytest`` runs.

Provider precedence: :func:`get_effective_llm_provider` honours an
explicit ``LLM_PROVIDER`` choice (``glm`` | ``opencode`` | ``gemini``)
and otherwise returns ``"glm"`` when :func:`is_glm_configured` is True,
else ``"opencode"`` when :func:`is_opencode_configured` is True, else
``"gemini"``. :func:`get_effective_llm_model` /
:func:`get_effective_llm_api_key` resolve accordingly. Backward-compat
wrappers :func:`get_gemini_model`, :func:`get_gemini_api_key`, and
:func:`is_gemini_configured` now delegate to the effective provider so
existing callers (worker, services) pick up GLM/OPENCODE precedence with
no code change (``get_gemini_*`` return *effective* values, not
Gemini-only ones; use the ``_get_gemini_*_only`` helpers for Gemini-only
lookups).

Safety: this module never prints, logs, or includes secret values
(GEMINI_API_KEY, OPENCODE_API_KEY/OPENCODE_KEY, GLM_API_KEY/ZAI_API_KEY, MAIL_SMTP_PASS,
SECRET_KEY) in prompts, logs, or errors. Logs may include the model name,
provider, and base-URL host only (never key material).
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

DEFAULT_GEMINI_MODEL = "gemma-4-31b-it"
DEFAULT_OPENCODE_MODEL = "muse-spark-1.3-contributor"
DEFAULT_OPENCODE_BASE_URL = "https://opencode.ai/inference/openai/v1"
DEFAULT_GLM_MODEL = "glm-5.3-flash"
DEFAULT_GLM_BASE_URL = "https://api.z.ai/api/paas/v4/"

# GLM-recommended sampling (vs 0.2 for the google-genai gemini/opencode path).
GLM_TEMPERATURE = 1.0
GLM_TOP_P = 0.95

# Shared placeholder set (mirrors ``.env.example``
# ``GEMINI_API_KEY=your_gemini_api_key_here``) plus common dev/test
# stand-ins and the GLM aliases. Comparison is case-insensitive on the
# stripped value.
_PLACEHOLDER_KEYS = frozenset(
    {
        "",
        "your_gemini_api_key_here",
        "your_opencode_key_here",
        "your_opencode_api_key_here",
        "your_glm_key_here",
        "your_zai_key_here",
        "change-me",
        "changeme",
        "test",
        "dummy",
        "placeholder",
    }
)


def _is_placeholder_key(key: str | None) -> bool:
    """True when ``key`` is missing or a known placeholder (never logs value)."""
    if not key:
        return True
    return key.strip().lower() in _PLACEHOLDER_KEYS

# Canonical import: `backend/` is on PYTHONPATH (see backend/tests/conftest.py).
# Track 1 exposes settings via `get_settings()` (lru_cached; a module-level
# `settings` singleton mirrors it) — resolve lazily so agents work offline
# without core, and always fall back to `os.environ`. Never import secret
# values at module scope.
def _get_app_settings() -> Any | None:
    """Return Track 1 settings or None (offline/CI-safe, never raises)."""
    try:
        from app.core.config import get_settings  # type: ignore

        return get_settings()
    except Exception:
        return None


# Once-per-process warning dedupe so a 12-criterion scorecard emits one
# WARNING instead of twelve. Keys: "missing_key" vs "transport_error".
_FALLBACK_WARNED: set[str] = set()


def _warn_once(key: str, msg: str, *args: Any) -> None:
    """Emit a WARNING log at most once per process for the given key."""
    if key in _FALLBACK_WARNED:
        return
    _FALLBACK_WARNED.add(key)
    logger.warning(msg, *args)


def reset_fallback_warnings_for_tests() -> None:
    """Clear once-per-process warning state (tests only)."""
    _FALLBACK_WARNED.clear()


def _get_gemini_model_only() -> str:
    """Gemini-only model lookup (no OPENCODE precedence).

    Prefers Track 1 settings (``GEMINI_MODEL``) then ``os.environ``;
    falls back to ``DEFAULT_GEMINI_MODEL`` (``gemma-4-31b-it``) when unset
    or empty so ``GEMINI_MODEL=`` still resolves to Gemma.
    """
    try:
        app_settings = _get_app_settings()
        if app_settings is not None:
            model = getattr(app_settings, "GEMINI_MODEL", None)
            if model:
                return str(model)
    except Exception:
        pass
    return os.environ.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL


def _get_gemini_key_only() -> str | None:
    """Gemini-only key lookup without ever logging its value."""
    try:
        app_settings = _get_app_settings()
        if app_settings is not None:
            key = getattr(app_settings, "GEMINI_API_KEY", None)
            if key:
                return str(key)
    except Exception:
        pass
    return os.environ.get("GEMINI_API_KEY")


def _is_gemini_key_configured() -> bool:
    """True only when a non-placeholder GEMINI_API_KEY is present."""
    return not _is_placeholder_key(_get_gemini_key_only())


def get_opencode_model() -> str:
    """Return configured OpenCode model name verbatim with safe default.

    The value is passed through **verbatim** to the OpenCode gateway —
    provider prefixes are never stripped. Accepted forms include::

        muse-spark-1.3-contributor
        glm-5.3-flash
        opencode-go/glm-5.3-flash
        z-ai/glm-5.3-flash

    Prefers Track 1 settings (``OPENCODE_MODEL``) then ``os.environ``;
    falls back to ``DEFAULT_OPENCODE_MODEL``
    (``muse-spark-1.3-contributor``) when unset or empty.
    """
    try:
        app_settings = _get_app_settings()
        if app_settings is not None:
            model = getattr(app_settings, "OPENCODE_MODEL", None)
            if model:
                return str(model)
    except Exception:
        pass
    return os.environ.get("OPENCODE_MODEL") or DEFAULT_OPENCODE_MODEL


def get_opencode_api_key() -> str | None:
    """Return OPENCODE_API_KEY (primary) or OPENCODE_KEY alias, never logging it.

    Lookup order: Track 1 settings ``OPENCODE_API_KEY``, then settings
    ``OPENCODE_KEY``, then ``os.environ`` ``OPENCODE_API_KEY``, then
    ``os.environ`` ``OPENCODE_KEY``. Returns None when none is set.
    """

    def _settings_first(*names: str) -> str | None:
        try:
            app_settings = _get_app_settings()
        except Exception:
            app_settings = None
        if app_settings is not None:
            for name in names:
                try:
                    val = getattr(app_settings, name, None)
                except Exception:
                    val = None
                if val:
                    return str(val)
        for name in names:
            val = os.environ.get(name)
            if val:
                return val
        return None

    return _settings_first("OPENCODE_API_KEY", "OPENCODE_KEY")


def is_opencode_configured() -> bool:
    """True only when a non-placeholder OPENCODE_API_KEY/OPENCODE_KEY is present.

    Placeholder set mirrors :data:`_PLACEHOLDER_KEYS` (including
    ``your_opencode_api_key_here``). Comparison is case-insensitive on the
    stripped value; the key itself is never logged.
    """
    return not _is_placeholder_key(get_opencode_api_key())


def _safe_url_host(url: str | None) -> str:
    """Return the host portion of ``url`` for safe logging (never key material).

    Base URLs never hold secrets, but only the host is emitted so query
    strings or accidental credentials can never leak into logs.
    """
    if not url:
        return ""
    try:
        from urllib.parse import urlparse

        return urlparse(url).netloc or url
    except Exception:
        return "?"


def get_opencode_base_url() -> str:
    """Return the OpenCode gateway base URL (never logs keys).

    Prefers Track 1 settings (``OPENCODE_BASE_URL``) then ``os.environ``.
    Empty/whitespace-only/unset values resolve to
    :data:`DEFAULT_OPENCODE_BASE_URL`
    (``https://opencode.ai/inference/openai/v1``) — an empty value means
    "default", never None. A non-empty value is a plain URL only — it
    never holds secrets, and key material must never be logged alongside
    it (log :func:`_safe_url_host` output only).
    """
    raw: str | None = None
    try:
        app_settings = _get_app_settings()
        if app_settings is not None:
            val = getattr(app_settings, "OPENCODE_BASE_URL", None)
            if val:
                raw = str(val)
    except Exception:
        pass
    if not raw or not raw.strip():
        raw = os.environ.get("OPENCODE_BASE_URL")
    if not raw or not raw.strip():
        return DEFAULT_OPENCODE_BASE_URL
    return raw.strip()


def _sampling_for_opencode_model(
    model: str | None, requested_temperature: float = 0.2
) -> tuple[float, float | None]:
    """Return ``(temperature, top_p)`` for an OpenCode gateway model.

    GLM models routed via the OpenCode gateway (``OPENCODE_MODEL`` such as
    ``glm-5.3-flash`` or ``opencode-go/glm-5.3-flash``) use the
    GLM-recommended ``temperature=1.0`` / ``top_p=0.95``; any other model
    keeps ``requested_temperature`` (default ``0.2``) with no ``top_p``
    override. Matching is case-insensitive on ``"glm"`` and never logs
    key material.
    """
    if model and "glm" in str(model).lower():
        return (GLM_TEMPERATURE, GLM_TOP_P)
    return (requested_temperature, None)


def is_opencode_openai_mode() -> bool:
    """True when the opencode provider routes via the OpenAI-compatible endpoint.

    Returns True only when the effective provider is ``"opencode"`` and the
    effective base URL (which defaults to
    :data:`DEFAULT_OPENCODE_BASE_URL`) looks OpenAI-compatible, i.e. it
    contains ``"/v1"`` or ``"opencode.ai/inference"``. Legacy custom
    gateway URLs without those markers keep the ``genai`` path. Used by
    :func:`_build_client` / :func:`call_gemini_structured` to decide
    between the ``genai`` path and the OpenAI-compatible gateway path.
    Only the provider/model/base-URL host (never key material) may appear
    in logs.
    """
    try:
        if get_effective_llm_provider() != "opencode":
            return False
    except Exception:
        return False
    try:
        base_url = get_opencode_base_url()
    except Exception:
        return False
    marker = (base_url or "").lower()
    return "/v1" in marker or "opencode.ai/inference" in marker


def get_glm_api_key() -> str | None:
    """Return GLM_API_KEY (primary) or ZAI_API_KEY alias, never logging it.

    Prefers Track 1 settings then ``os.environ``: ``GLM_API_KEY`` first,
    ``ZAI_API_KEY`` second. Returns None when neither is set.
    """

    def _settings_first(*names: str) -> str | None:
        try:
            app_settings = _get_app_settings()
        except Exception:
            app_settings = None
        if app_settings is not None:
            for name in names:
                try:
                    val = getattr(app_settings, name, None)
                except Exception:
                    val = None
                if val:
                    return str(val)
        for name in names:
            val = os.environ.get(name)
            if val:
                return val
        return None

    return _settings_first("GLM_API_KEY", "ZAI_API_KEY")


def get_glm_model() -> str:
    """Return configured GLM model name with safe default.

    Prefers Track 1 settings (``GLM_MODEL``) then ``os.environ``;
    falls back to ``DEFAULT_GLM_MODEL`` (``glm-5.3-flash``) when unset
    or empty.
    """
    try:
        app_settings = _get_app_settings()
        if app_settings is not None:
            model = getattr(app_settings, "GLM_MODEL", None)
            if model:
                return str(model)
    except Exception:
        pass
    return os.environ.get("GLM_MODEL") or DEFAULT_GLM_MODEL


def get_glm_base_url() -> str:
    """Return configured GLM base URL with safe Zhipu default.

    Prefers Track 1 settings (``GLM_BASE_URL``) then ``os.environ``;
    falls back to ``DEFAULT_GLM_BASE_URL``
    (``https://api.z.ai/api/paas/v4/``) when unset or empty.
    """
    try:
        app_settings = _get_app_settings()
        if app_settings is not None:
            for name in ("GLM_BASE_URL", "ZAI_BASE_URL"):
                try:
                    val = getattr(app_settings, name, None)
                except Exception:
                    val = None
                if val:
                    return str(val)
    except Exception:
        pass
    return (
        os.environ.get("GLM_BASE_URL")
        or os.environ.get("ZAI_BASE_URL")
        or DEFAULT_GLM_BASE_URL
    )


def is_glm_configured() -> bool:
    """True only when a non-placeholder GLM/ZAI key is present.

    Accepts ``GLM_API_KEY`` (primary) or its ``ZAI_API_KEY`` alias.
    Comparison is case-insensitive on the stripped value against
    :data:`_PLACEHOLDER_KEYS` (which includes ``your_glm_key_here`` /
    ``your_zai_key_here``); the key itself is never logged.
    """
    return not _is_placeholder_key(get_glm_api_key())


def get_llm_provider() -> str:
    """Return the normalized requested ``LLM_PROVIDER`` (never logs keys).

    Reads Track 1 settings (``LLM_PROVIDER``) then ``os.environ``;
    one of ``auto`` | ``glm`` | ``opencode`` | ``gemini`` (lower-cased,
    stripped). Unknown or empty values resolve to ``"auto"``.
    """
    raw: str | None = None
    try:
        app_settings = _get_app_settings()
        if app_settings is not None:
            val = getattr(app_settings, "LLM_PROVIDER", None)
            if val:
                raw = str(val)
    except Exception:
        pass
    if not raw:
        raw = os.environ.get("LLM_PROVIDER")
    normalized = (raw or "auto").strip().lower()
    if normalized in ("glm", "opencode", "gemini"):
        return normalized
    return "auto"


def get_effective_llm_provider() -> str:
    """Return the active provider honouring ``LLM_PROVIDER``.

    An explicit ``LLM_PROVIDER`` (``glm`` | ``opencode`` | ``gemini``)
    is honoured as-is (even when its key is missing — the call then
    degrades to the deterministic fallback). ``auto`` (default) uses
    GLM > OPENCODE > GEMINI order: ``"glm"`` when GLM is configured,
    else ``"opencode"`` when OpenCode is configured, else ``"gemini"``.
    """
    requested = get_llm_provider()
    if requested in ("glm", "opencode", "gemini"):
        return requested
    if is_glm_configured():
        return "glm"
    if is_opencode_configured():
        return "opencode"
    return "gemini"


def get_effective_llm_model() -> str:
    """Return the effective model for the active provider.

    GLM provider -> :func:`get_glm_model` (default
    ``glm-5.3-flash``); OpenCode provider -> :func:`get_opencode_model`
    (default ``muse-spark-1.3-contributor``); Gemini provider ->
    Gemini-only lookup (default ``gemma-4-31b-it``).
    """
    provider = get_effective_llm_provider()
    if provider == "glm":
        return get_glm_model()
    if provider == "opencode":
        return get_opencode_model()
    return _get_gemini_model_only()


def get_effective_llm_api_key() -> str | None:
    """Return the effective API key (GLM > OPENCODE > GEMINI, never log value)."""
    provider = get_effective_llm_provider()
    if provider == "glm":
        return get_glm_api_key()
    if provider == "opencode":
        return get_opencode_api_key()
    return _get_gemini_key_only()


def get_gemini_model() -> str:
    """Backward-compat wrapper returning the effective model.

    Delegates to :func:`get_effective_llm_model` so existing callers
    (worker/services) automatically honour provider precedence with no
    code change. Returns the GLM model when the GLM provider is active,
    ``muse-spark-1.3-contributor`` when the OpenCode provider is active,
    else the configured Gemini/Gemma model. NOTE: despite the historic
    name this returns *effective* (not Gemini-only) values.
    """
    return get_effective_llm_model()


def get_gemini_api_key() -> str | None:
    """Backward-compat wrapper returning the effective key (never log value).

    Delegates to :func:`get_effective_llm_api_key`: GLM_API_KEY/ZAI_API_KEY
    when the GLM provider is active, OPENCODE_KEY when the OpenCode
    provider is active, else GEMINI_API_KEY. NOTE: despite the historic
    name this returns the *effective* key for the active provider.
    """
    return get_effective_llm_api_key()


def is_gemini_configured() -> bool:
    """Backward-compat wrapper: True when any provider is configured.

    Returns True if GLM_API_KEY/ZAI_API_KEY *or* OPENCODE_KEY *or*
    GEMINI_API_KEY holds a non-placeholder value (``auto`` precedence is
    GLM > OPENCODE > GEMINI). Kept under the historic ``is_gemini_*``
    name so worker gates (``is_gemini_enabled``) need no change. The key
    itself is never logged.
    """
    return bool(
        is_glm_configured() or is_opencode_configured() or _is_gemini_key_configured()
    )


class GeminiUnavailableError(RuntimeError):
    """Raised when Gemini cannot be called (no key, missing SDK, transport error)."""


def _strip_code_fences(text: str) -> str:
    """Remove Markdown ```json / ``` wrappers and surrounding whitespace.

    Gemma (gemma-4-31b-it) sometimes returns structured JSON wrapped in
    fenced code blocks (`````json ... `````) which would otherwise cause a
    spurious ``json.loads`` failure and an unnecessary deterministic fallback.
    This helper unwraps such fences idempotently; plain JSON passes through
    unchanged (besides ``strip()``).
    """
    s = (text or "").strip()
    if not s.startswith("```"):
        return s
    # Drop the opening fence line (e.g. ``` or ```json).
    first_nl = s.find("\n")
    if first_nl == -1:
        # Single-line fence with no newline, e.g. "```json {...}```".
        inner = s[3:].strip()
        if inner.lower().startswith("json"):
            inner = inner[4:].strip()
        if inner.endswith("```"):
            inner = inner[:-3].strip()
        return inner
    s = s[first_nl + 1 :]
    # Drop the trailing fence if present.
    stripped = s.rstrip()
    if stripped.endswith("```"):
        stripped = stripped[:-3]
    return stripped.strip()


def _parse_json_object(text: str) -> dict[str, Any]:
    """Fence-strip then parse ``text``; require a top-level JSON object."""
    cleaned = _strip_code_fences(text)
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError) as exc:
        raise GeminiUnavailableError(
            "Gemini returned non-JSON output; using deterministic fallback."
        ) from exc
    if not isinstance(data, dict):
        raise GeminiUnavailableError(
            "Gemini returned non-object JSON; using deterministic fallback."
        )
    return data


def _transient_error_haystack(exc: BaseException) -> str:
    """Upper-cased haystack of exception identity/status for retry detection."""
    parts: list[str] = [type(exc).__name__, str(exc)]
    for attr in ("status", "code", "status_code", "error_code"):
        try:
            val = getattr(exc, attr, None)
        except Exception:
            val = None
        if val is not None:
            parts.append(str(val))
    # google-genai ServerError may nest details in args.
    try:
        for arg in getattr(exc, "args", ()):  # type: ignore[union-attr]
            parts.append(str(arg))
    except Exception:
        pass
    return " ".join(parts).upper()


def _is_transient_server_error(exc: BaseException) -> bool:
    """True for retryable 5xx-style transient server errors.

    Detects via exception message/status/code containing 500/503/529/
    UNAVAILABLE/INTERNAL/OVERLOADED (covers ``ServerError`` and
    ``503 UNAVAILABLE`` from Gemma ``generateContent`` as well as
    ``529 overloaded`` from the GLM OpenAI-compatible endpoint). Never
    inspects secret values.
    """
    haystack = _transient_error_haystack(exc)
    return (
        "500" in haystack
        or "503" in haystack
        or "529" in haystack
        or "UNAVAILABLE" in haystack
        or "OVERLOADED" in haystack
        or "INTERNAL" in haystack
    )


def _server_code_label(exc: BaseException) -> str:
    """Best-effort status label for error messages (never includes secrets)."""
    haystack = _transient_error_haystack(exc)
    if "503" in haystack or "UNAVAILABLE" in haystack:
        return "503"
    if "529" in haystack or "OVERLOADED" in haystack:
        return "529"
    if "500" in haystack or "INTERNAL" in haystack:
        return "500"
    return "500/503/529"


def _build_client() -> Any:
    """Build the effective LLM client or raise GeminiUnavailableError.

    Provider-aware constructor (never logs key material; logs may include
    only the provider, model name, and base-URL host):

    - ``glm`` provider callers use :func:`_build_glm_client` directly and
      never reach this function via :func:`call_gemini_structured`.
    - ``opencode`` provider defaults to the OpenAI-compatible inference
      endpoint (:data:`DEFAULT_OPENCODE_BASE_URL` =
      ``https://opencode.ai/inference/openai/v1``) via
      ``OpenAI(api_key=..., base_url=...)`` (lazy import). The gateway
      model string (``OPENCODE_MODEL``) is always sent **verbatim** —
      accepted forms::

          muse-spark-1.3-contributor
          kimi-k2.6
          glm-5.3-flash
          opencode-go/glm-5.3-flash

      i.e. ``opencode-go/`` / ``z-ai/`` prefixes are never stripped. When
      the ``openai`` SDK is unavailable this raises
      :class:`GeminiUnavailableError` (callers degrade to the
      deterministic ``needs_review`` fallback) instead of falling back to
      ``genai.Client`` with an opencode key — sending an opencode key to
      Google surfaces as ``400 API_KEY_INVALID``. The client is never
      constructed with a crashing error; failures always surface as
      :class:`GeminiUnavailableError`.
    - ``opencode`` provider with a *legacy* custom ``OPENCODE_BASE_URL``
      that is not OpenAI-compatible (no ``"/v1"`` /
      ``"opencode.ai/inference"`` marker) targets the custom gateway
      endpoint via ``genai.Client(api_key=...,
      http_options={"base_url": url})`` (``base_url`` kwarg fallback for
      older SDK shapes).
    - The ``gemini`` provider keeps the plain
      ``genai.Client(api_key=...)`` behavior.

    Only the model name, provider, and base-URL host (never key material)
    may appear in logs/errors.
    """
    if not is_gemini_configured():
        raise GeminiUnavailableError(
            "GEMINI_API_KEY/OPENCODE_API_KEY is not configured; using deterministic fallback."
        )
    provider: str
    try:
        provider = get_effective_llm_provider()
    except Exception:
        provider = "gemini"
    if provider == "opencode":
        base_url = get_opencode_base_url()
        key = get_opencode_api_key()
        if _is_placeholder_key(key):
            raise GeminiUnavailableError(
                "OPENCODE_API_KEY/OPENCODE_KEY is not configured; "
                "using deterministic fallback."
            )
        if is_opencode_openai_mode():
            # Default path: OpenAI-compatible inference endpoint with the
            # model string passed verbatim. Never route an opencode key
            # through genai (Google rejects it with 400 API_KEY_INVALID).
            try:
                from openai import OpenAI  # type: ignore
            except Exception as exc:
                raise GeminiUnavailableError(
                    f"openai SDK unavailable: {type(exc).__name__}; "
                    "using deterministic fallback."
                ) from exc
            logger.debug(
                "opencode OpenAI-compatible client (provider=%s model=%s base_host=%s).",
                provider,
                get_opencode_model(),
                _safe_url_host(base_url),
            )
            return OpenAI(api_key=key, base_url=base_url)
        # Legacy path: non-OpenAI custom gateway URL via genai only.
        try:
            from google import genai  # type: ignore
        except Exception as exc:
            raise GeminiUnavailableError(
                f"google-genai SDK unavailable: {exc}; using deterministic fallback."
            ) from exc
        logger.debug(
            "opencode legacy genai client (provider=%s model=%s base_host=%s).",
            provider,
            get_opencode_model(),
            _safe_url_host(base_url),
        )
        try:
            return genai.Client(api_key=key, http_options={"base_url": base_url})
        except Exception:
            try:
                return genai.Client(api_key=key, base_url=base_url)  # type: ignore[call-arg]
            except Exception as exc:
                raise GeminiUnavailableError(
                    f"opencode legacy gateway client failed: {type(exc).__name__}; "
                    "using deterministic fallback."
                ) from exc
    try:
        from google import genai  # type: ignore
    except Exception as exc:
        raise GeminiUnavailableError(
            f"google-genai SDK unavailable: {exc}; using deterministic fallback."
        ) from exc
    # Provider-aware: effective key honours GLM > OPENCODE > GEMINI.
    return genai.Client(api_key=get_effective_llm_api_key())


def _build_opencode_openai_client() -> Any:
    """Build an OpenAI-compatible client for the opencode gateway.

    Uses ``OPENCODE_API_KEY`` (or its ``OPENCODE_KEY`` alias) against the
    effective base URL (``OPENCODE_BASE_URL`` or
    :data:`DEFAULT_OPENCODE_BASE_URL` =
    ``https://opencode.ai/inference/openai/v1``). The ``openai`` package
    is imported lazily so ``pytest`` without it still passes — callers
    degrade to the deterministic fallback via
    :class:`GeminiUnavailableError` (``needs_review``, never a crash).
    Only the model name, provider, and base-URL host (never key material)
    may appear in logs/errors.
    """
    key = get_opencode_api_key()
    if _is_placeholder_key(key):
        raise GeminiUnavailableError(
            "OPENCODE_API_KEY/OPENCODE_KEY is not configured; using deterministic fallback."
        )
    base_url = get_opencode_base_url()
    if not base_url:  # Defensive: get_opencode_base_url() always defaults.
        raise GeminiUnavailableError(
            "OPENCODE_BASE_URL is not configured; using deterministic fallback."
        )
    try:
        from openai import OpenAI  # type: ignore
    except Exception as exc:
        raise GeminiUnavailableError(
            f"openai SDK unavailable: {exc}; using deterministic fallback."
        ) from exc
    return OpenAI(api_key=key, base_url=base_url)


def _is_openai_compatible_client(client: Any) -> bool:
    """True when ``client`` is OpenAI-compatible (chat.completions)."""
    try:
        chat = getattr(client, "chat", None)
        completions = getattr(chat, "completions", None) if chat is not None else None
        return callable(getattr(completions, "create", None))
    except Exception:
        return False


def _call_opencode_openai_structured(
    *,
    system_instruction: str,
    user_prompt: str,
    max_output_tokens: int = 4096,
    temperature: float = 0.2,
    client: Any | None = None,
) -> dict[str, Any]:
    """Call the opencode gateway (OpenAI-compatible) and parse JSON.

    Uses ``client.chat.completions.create`` with system/user ``messages``
    (``OpenAI(api_key=OPENCODE_API_KEY, base_url=<inference /v1 URL>)``).
    Sends ``OPENCODE_MODEL`` **verbatim** (``opencode-go/`` / ``z-ai/``
    prefixes preserved, e.g. ``kimi-k2.6`` or
    ``opencode-go/glm-5.3-flash``). Sampling follows
    :func:`_sampling_for_opencode_model`: models containing ``"glm"``
    (case-insensitive) use GLM-recommended ``temperature=1.0`` /
    ``top_p=0.95``, otherwise the caller's ``temperature`` (default
    ``0.2``) with no ``top_p`` override. Requests JSON via
    ``response_format={"type": "json_object"}`` when the installed
    ``openai`` SDK supports it (dropped on ``TypeError``), reuses
    fence-strip parsing (:func:`_parse_json_object`), the transient
    500/503/529 retry (initial attempt + 2 retries, 1s then 2s backoff)
    plus one final plain-JSON safe retry (``response_format`` dropped).
    Raises :class:`GeminiUnavailableError` on missing key/URL/SDK/transport/
    parse issues (callers fall back to ``needs_review``, never crash).
    Never includes secrets (only model/provider/base-URL host may appear
    in errors).
    """
    live_client = client if client is not None else _build_opencode_openai_client()
    model = get_opencode_model()
    eff_temperature, eff_top_p = _sampling_for_opencode_model(
        model, requested_temperature=temperature
    )
    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": user_prompt},
    ]
    base_kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": eff_temperature,
        "max_tokens": max_output_tokens,
        "response_format": {"type": "json_object"},
    }
    if eff_top_p is not None:
        base_kwargs["top_p"] = eff_top_p
    response: Any = None
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            response = _glm_chat_create(live_client, base_kwargs)
            last_exc = None
            break
        except TypeError as exc:
            raise GeminiUnavailableError(
                f"OpenCode request failed ({type(exc).__name__} "
                f"code={_server_code_label(exc)} model={model}); "
                "using fallback."
            ) from exc
        except Exception as exc:
            last_exc = exc
            if not _is_transient_server_error(exc):
                raise GeminiUnavailableError(
                    f"OpenCode request failed ({type(exc).__name__} "
                    f"code={_server_code_label(exc)} model={model}); "
                    "using fallback."
                ) from exc
            if attempt < 2:
                time.sleep(1 if attempt == 0 else 2)
                continue
            break

    if response is not None:
        return _parse_json_object(_glm_response_text(response))

    # Retries exhausted on a transient 500/503/529: one safe retry as
    # plain JSON (no response_format), mirroring the Gemma-safe retry.
    assert last_exc is not None
    plain_kwargs = dict(base_kwargs)
    plain_kwargs.pop("response_format", None)
    try:
        safe_response = _glm_chat_create(live_client, plain_kwargs)
    except Exception as exc:
        raise GeminiUnavailableError(
            f"OpenCode request failed ({type(exc).__name__} "
            f"code={_server_code_label(exc)} model={model}); "
            "using fallback."
        ) from exc
    return _parse_json_object(_glm_response_text(safe_response))


def _build_glm_client() -> Any:
    """Build an OpenAI-compatible GLM client (never logs key material).

    Uses ``GLM_API_KEY`` (or its ``ZAI_API_KEY`` alias) against the
    configured ``GLM_BASE_URL`` (default
    ``https://api.z.ai/api/paas/v4/``). The ``openai`` package is
    imported lazily so ``pytest`` without it still passes — callers
    degrade to the deterministic fallback via
    :class:`GeminiUnavailableError`. Only the model name and provider
    (never key material) may appear in logs/errors.
    """
    key = get_glm_api_key()
    if _is_placeholder_key(key):
        raise GeminiUnavailableError(
            "GLM_API_KEY/ZAI_API_KEY is not configured; using deterministic fallback."
        )
    try:
        from openai import OpenAI  # type: ignore
    except Exception as exc:
        raise GeminiUnavailableError(
            f"openai SDK unavailable: {exc}; using deterministic fallback."
        ) from exc
    return OpenAI(api_key=key, base_url=get_glm_base_url())


def _glm_chat_create(client: Any, base_kwargs: dict[str, Any]) -> Any:
    """Call ``client.chat.completions.create`` dropping unsupported kwargs.

    Older ``openai`` SDK versions may not accept ``response_format`` or
    ``max_tokens``; on ``TypeError`` naming the offending kwarg, drop it
    and retry (plain prompt + fence-strip parse still applies downstream).
    Any other ``TypeError`` propagates to the caller.
    """
    kwargs = dict(base_kwargs)
    while True:
        try:
            return client.chat.completions.create(**kwargs)
        except TypeError as exc:
            msg = str(exc).lower()
            if "response_format" in msg and "response_format" in kwargs:
                kwargs.pop("response_format")
                continue
            if "max_tokens" in msg and "max_tokens" in kwargs:
                kwargs.pop("max_tokens")
                continue
            raise


def _glm_response_text(response: Any) -> str:
    """Extract assistant text from an OpenAI-style chat completion."""
    try:
        choices = getattr(response, "choices", None) or []
        if choices:
            message = getattr(choices[0], "message", None)
            content = getattr(message, "content", None) if message is not None else None
            if isinstance(content, str) and content.strip():
                return content
            # Some SDK versions return content blocks (list of parts).
            if isinstance(content, list):
                parts: list[str] = []
                for part in content:
                    if isinstance(part, str):
                        parts.append(part)
                    else:
                        text = getattr(part, "text", None)
                        if isinstance(text, str):
                            parts.append(text)
                if parts:
                    return "".join(parts)
    except Exception:
        pass
    return getattr(response, "text", "") or ""


def _call_glm_structured(
    *,
    system_instruction: str,
    user_prompt: str,
    max_output_tokens: int = 4096,
) -> dict[str, Any]:
    """Call GLM (OpenAI-compatible) and return a parsed JSON object.

    Uses system/user message separation, the GLM-recommended
    ``temperature=1.0`` / ``top_p=0.95``, and requests JSON via
    ``response_format={"type": "json_object"}`` when the installed
    ``openai`` SDK supports it (otherwise plain + fence-strip parse).
    Reuses :func:`_parse_json_object` and the transient 500/503/529
    retry (initial attempt + 2 retries, 1s then 2s backoff) plus one
    final plain-JSON safe retry when retries are exhausted. Raises
    :class:`GeminiUnavailableError` on missing key/SDK/transport/parse
    issues so callers fall back deterministically. Never includes
    secrets (only model/provider may appear in errors).
    """
    client = _build_glm_client()
    model = get_glm_model()
    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": user_prompt},
    ]
    base_kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": GLM_TEMPERATURE,
        "top_p": GLM_TOP_P,
        "max_tokens": max_output_tokens,
        "response_format": {"type": "json_object"},
    }
    response: Any = None
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            response = _glm_chat_create(client, base_kwargs)
            last_exc = None
            break
        except TypeError as exc:
            raise GeminiUnavailableError(
                f"GLM request failed ({type(exc).__name__} "
                f"code={_server_code_label(exc)} model={model}); "
                "using fallback."
            ) from exc
        except Exception as exc:
            last_exc = exc
            if not _is_transient_server_error(exc):
                raise GeminiUnavailableError(
                    f"GLM request failed ({type(exc).__name__} "
                    f"code={_server_code_label(exc)} model={model}); "
                    "using fallback."
                ) from exc
            if attempt < 2:
                time.sleep(1 if attempt == 0 else 2)
                continue
            break

    if response is not None:
        return _parse_json_object(_glm_response_text(response))

    # Retries exhausted on a transient 500/503/529: one safe retry as
    # plain JSON (no response_format), mirroring the Gemma-safe retry.
    assert last_exc is not None
    plain_kwargs = dict(base_kwargs)
    plain_kwargs.pop("response_format", None)
    try:
        safe_response = _glm_chat_create(client, plain_kwargs)
    except Exception as exc:
        raise GeminiUnavailableError(
            f"GLM request failed ({type(exc).__name__} "
            f"code={_server_code_label(exc)} model={model}); "
            "using fallback."
        ) from exc
    return _parse_json_object(_glm_response_text(safe_response))


def call_gemini_structured(
    *,
    system_instruction: str,
    user_prompt: str,
    response_schema: Any,
    temperature: float = 0.2,
    max_output_tokens: int = 4096,
) -> dict[str, Any]:
    """Call the effective LLM (GLM > OpenCode > Gemini) with enforced JSON output.

    GLM provider (``LLM_PROVIDER=glm`` or ``auto`` with ``GLM_API_KEY`` /
    ``ZAI_API_KEY`` set) routes to the OpenAI-compatible Zhipu endpoint
    via :func:`_call_glm_structured` (``glm-5.3-flash`` by default,
    ``temperature=1.0`` / ``top_p=0.95`` per GLM recommendations,
    ``response_format={"type": "json_object"}`` when supported).
    OpenCode provider (``LLM_PROVIDER=opencode`` or ``auto`` with
    ``OPENCODE_API_KEY``/``OPENCODE_KEY`` set) sends ``OPENCODE_MODEL``
    **verbatim** to the gateway — accepted forms
    ``muse-spark-1.3-contributor``, ``kimi-k2.6``,
    ``glm-5.3-flash``, ``opencode-go/glm-5.3-flash`` (``opencode-go/`` /
    ``z-ai/`` prefixes never stripped). By default (base URL unset, empty,
    or OpenAI-compatible, i.e. containing ``"/v1"`` or
    ``"opencode.ai/inference"``) it routes to
    :func:`_call_opencode_openai_structured`
    (``OpenAI(api_key, base_url)`` + ``chat.completions.create`` with
    system/user messages and ``response_format={"type": "json_object"}``
    handling); only a legacy non-OpenAI ``OPENCODE_BASE_URL`` keeps the
    ``genai`` ``GenerateContentConfig(response_mime_type="application/json",
    response_schema=...)`` path. GLM models
    routed via the opencode gateway (model contains ``"glm"``,
    case-insensitive) use ``temperature=1.0`` / ``top_p=0.95``,
    otherwise the caller's ``temperature`` (default ``0.2``). Otherwise
    the effective model is ``gemma-4-31b-it`` (see
    :func:`_get_gemini_model_only`); Gemma 4-IT supports
    ``generateContent`` via the Gemini API with the same shape. Raises
    :class:`GeminiUnavailableError` on missing key/SDK/transport/parse issues
    so callers can fall back deterministically. Never includes secrets
    (only the model/provider name and base-URL host may appear in errors).
    """
    if get_effective_llm_provider() == "glm":
        return _call_glm_structured(
            system_instruction=system_instruction,
            user_prompt=user_prompt,
            max_output_tokens=max_output_tokens,
        )
    if is_opencode_openai_mode():
        # Default opencode path: OpenAI-compatible inference endpoint.
        # Routed explicitly (not via _build_client) so no google-genai
        # import is required; missing openai SDK surfaces as
        # GeminiUnavailableError -> deterministic needs_review fallback.
        return _call_opencode_openai_structured(
            system_instruction=system_instruction,
            user_prompt=user_prompt,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        )
    client = _build_client()
    if _is_openai_compatible_client(client):
        # Opencode gateway with a custom OPENCODE_BASE_URL that fell back
        # to the OpenAI-compatible transport: reuse the openai structured
        # path (fence-strip + 500/503/529 retry + safe retry without
        # response_format). Model is sent verbatim; GLM models use 1.0/0.95.
        return _call_opencode_openai_structured(
            system_instruction=system_instruction,
            user_prompt=user_prompt,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            client=client,
        )
    try:
        from google.genai import types  # type: ignore
    except Exception as exc:
        raise GeminiUnavailableError(
            f"google.genai.types unavailable: {exc}"
        ) from exc

    model = get_effective_llm_model()
    eff_temperature, eff_top_p = temperature, None
    if get_effective_llm_provider() == "opencode":
        eff_temperature, eff_top_p = _sampling_for_opencode_model(
            model, requested_temperature=temperature
        )
    config_kwargs: dict[str, Any] = {
        "response_mime_type": "application/json",
        "response_schema": response_schema,
        "system_instruction": system_instruction,
        "temperature": eff_temperature,
        "max_output_tokens": max_output_tokens,
    }
    if eff_top_p is not None:
        config_kwargs["top_p"] = eff_top_p
    config = types.GenerateContentConfig(**config_kwargs)
    # Retry transient 500/503 (Gemma generateContent flakiness) with backoff:
    # initial attempt + 2 retries (1s, 2s). Only retryable errors loop;
    # anything else fails fast with status + model in the message (no secrets).
    response: Any = None
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model,
                contents=user_prompt,
                config=config,
            )
            last_exc = None
            break
        except Exception as exc:
            last_exc = exc
            if not _is_transient_server_error(exc):
                raise GeminiUnavailableError(
                    f"Gemini request failed ({type(exc).__name__} "
                    f"code={_server_code_label(exc)} model={model}); "
                    "using fallback."
                ) from exc
            if attempt < 2:
                # Backoff 1s then 2s before the next retry.
                time.sleep(1 if attempt == 0 else 2)
                continue
            break

    if response is not None:
        # SDK may already parse into response.parsed when response_schema given.
        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            if hasattr(parsed, "model_dump"):
                return dict(parsed.model_dump())
            if isinstance(parsed, dict):
                return parsed
        text = getattr(response, "text", "") or ""
        return _parse_json_object(text)

    # Retries exhausted on a transient 500/503: one Gemma-safe retry without
    # response_schema (schema enforcement trips Gemma 4-IT), inlining the
    # system instruction into contents. Keeps response_mime_type as
    # application/json, caps tokens 4096->2048, and parses via the same
    # fence-strip path.
    assert last_exc is not None
    try:
        from google.genai import types as _types  # type: ignore  # noqa: F811

        safe_kwargs: dict[str, Any] = {
            "response_mime_type": "application/json",
            "temperature": eff_temperature,
            "max_output_tokens": 2048,
        }
        if eff_top_p is not None:
            safe_kwargs["top_p"] = eff_top_p
        safe_config = _types.GenerateContentConfig(**safe_kwargs)
    except Exception as exc:
        raise GeminiUnavailableError(
            f"Gemini request failed ({type(last_exc).__name__} "
            f"code={_server_code_label(last_exc)} model={model}); "
            "using fallback."
        ) from last_exc
    try:
        safe_response = client.models.generate_content(
            model=model,
            contents=f"{system_instruction}\n\n{user_prompt}",
            config=safe_config,
        )
    except Exception as exc:
        raise GeminiUnavailableError(
            f"Gemini request failed ({type(exc).__name__} "
            f"code={_server_code_label(exc)} model={model}); "
            "using fallback."
        ) from exc

    safe_parsed = getattr(safe_response, "parsed", None)
    if safe_parsed is not None:
        if hasattr(safe_parsed, "model_dump"):
            return dict(safe_parsed.model_dump())
        if isinstance(safe_parsed, dict):
            return safe_parsed
    safe_text = getattr(safe_response, "text", "") or ""
    return _parse_json_object(safe_text)


def call_llm_structured(
    *,
    system_instruction: str,
    user_prompt: str,
    response_schema: Any,
    temperature: float = 0.2,
    max_output_tokens: int = 4096,
) -> dict[str, Any]:
    """Provider-aware alias of :func:`call_gemini_structured`.

    Canonical entry point for new callers: routes to GLM
    (OpenAI-compatible) when the GLM provider is active, else to the
    google-genai Gemini/OpenCode path. :func:`call_gemini_structured`
    is retained as the historic name and delegates here logically
    (both share the same implementation/branching).
    """
    return call_gemini_structured(
        system_instruction=system_instruction,
        user_prompt=user_prompt,
        response_schema=response_schema,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )


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
    """Run an effective-LLM structured call, degrading to ``fallback`` on failure.

    ``prompt_builder`` returns ``(system_instruction, user_prompt)``.
    ``parse`` validates the raw dict into the agent's Pydantic output.
    ``fallback`` receives the causing exception (or None) and must return a
    valid schema instance (typically ``needs_review`` / low confidence).
    Honours GLM > OPENCODE > GEMINI precedence (or an explicit
    ``LLM_PROVIDER``) via :func:`get_effective_llm_model`.
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
        # Visible-but-safe fallback: WARNING (once per process, not per
        # criterion) distinguishing missing key vs transport/SDK failure.
        # Includes the model name + provider only — never key material.
        if not is_gemini_configured():
            _warn_once(
                "missing_key",
                "LLM unavailable (GLM_API_KEY/ZAI_API_KEY, OPENCODE_API_KEY/OPENCODE_KEY, or "
                "GEMINI_API_KEY missing or placeholder); using deterministic "
                "fallback (provider=%s model=%s). Set a valid key to enable "
                "live scoring; fallback proposals use score_state=needs_review.",
                get_effective_llm_provider(),
                get_effective_llm_model(),
            )
        else:
            _warn_once(
                "transport_error",
                "LLM request unavailable (%s); using deterministic "
                "fallback (provider=%s model=%s). Fallback proposals use "
                "score_state=needs_review.",
                type(exc.__cause__ or exc).__name__,
                get_effective_llm_provider(),
                get_effective_llm_model(),
            )
        return fallback(exc)
    except Exception as exc:  # validation or unexpected error -> safe fallback
        _warn_once(
            "parse_error",
            "Agent structured-output parse failed (%s); using fallback "
            "(provider=%s model=%s).",
            type(exc).__name__,
            get_effective_llm_provider(),
            get_effective_llm_model(),
        )
        return fallback(exc)


ADVISORY_NOTICE = (
    "AI estimates are advisory only and never constitute an official course grade. "
    "ai_proposed_points and ai_reasoning are preserved even after human override."
)
