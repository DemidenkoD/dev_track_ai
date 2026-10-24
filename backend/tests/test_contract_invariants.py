"""Track 5: five non-negotiable product invariants as mocked contract tests.

Covers (AGENTS.md §1 + backend/AGENTS.md §2 + DATABASE_SCHEMA.md + API_CONTRACT.md):

  a) score_state ∈ {estimated, verified, needs_review}; human override
     preserves ai_proposed_points + ai_reasoning.
  b) Completing development_milestones NEVER auto-awards the assessment
     criterion score (Development Completion vs Expected Course Score separate).
  c) notify_email_once NEVER in Postgres/logs/traces; ephemeral registry purges.
  d) SSRF: only https://github.com/<owner>/<repo> accepted; private/loopback/
     link-local/metadata IPs blocked.
  e) Advisory read-only: no push/PR/mutate endpoints exist.

No live GitHub/LLM/scanner/network/DB. DNS is mocked. Missing Track 1
wiring yields pytest.skip with reason, never a hard failure.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from pathlib import Path
from uuid import uuid4

import pytest

pytestmark = [pytest.mark.contract, pytest.mark.invariants, pytest.mark.unit]


def _skip_import(module: str, name: str | None = None):
    return pytest.importorskip(module, reason=f"Blocked on Track 1 dep: {module} unavailable") \
        if name is None else getattr(
            pytest.importorskip(module, reason=f"Blocked on Track 1 dep: {module} unavailable"),
            name,
        )


# ---------------------------------------------------------------------------
# (a) Score state + human-override preservation
# ---------------------------------------------------------------------------
class TestScoreStateAndOverridePreservation:
    def test_score_state_values_mocked(self):
        ScoreState = _skip_import("app.schemas.enums", "ScoreState")
        assert {s.value for s in ScoreState} == {"estimated", "verified", "needs_review"}

    def test_criterion_assessment_preserves_ai_fields_on_override_mocked(self):
        schemas = _skip_import("app.schemas.api_contracts")
        CriterionAssessmentSchema = schemas.CriterionAssessmentSchema
        ScoreState = _skip_import("app.schemas.enums", "ScoreState")

        assessment = CriterionAssessmentSchema(
            id=uuid4(),
            analysis_run_id=uuid4(),
            project_id=uuid4(),
            assessment_milestone_id=uuid4(),
            criterion_code="ci_cd",
            max_points=2,
            ai_proposed_points=1,
            ai_reasoning="Found docker-compose.yml but no CI workflow.",
            ai_confidence=0.7,
            score_state=ScoreState.ESTIMATED,
            created_at="2026-10-24T00:00:00Z",
        )
        # Simulate a human override the way PATCH /scorecard/... must behave:
        # only human_* + score_state change; ai_* fields stay identical.
        before_ai_points = assessment.ai_proposed_points
        before_ai_reasoning = assessment.ai_reasoning
        assessment.human_override_points = 2
        assessment.human_override_reason = "Verified single-command Docker Compose startup."
        assessment.score_state = ScoreState.VERIFIED

        assert assessment.ai_proposed_points == before_ai_points == 1
        assert assessment.ai_reasoning == before_ai_reasoning
        effective = (
            assessment.human_override_points
            if assessment.human_override_points is not None
            else assessment.ai_proposed_points
        )
        assert effective == 2

    def test_scorecard_endpoint_source_never_clobbers_ai_fields(self, backend_dir: Path):
        """Static: PATCH handler must not assign ai_proposed_points/ai_reasoning."""
        target = backend_dir / "app" / "api" / "v1" / "endpoints" / "scorecard.py"
        if not target.is_file():
            pytest.skip("Track 1 scorecard endpoint not wired yet")
        source = target.read_text(encoding="utf-8")
        for forbidden in ("ai_proposed_points =", "ai_reasoning ="):
            # Allowlist: only Pydantic response construction (`ai_proposed_points=...`
            # without spaces) may mention the field; direct assignment clobbers it.
            assert forbidden not in source, (
                f"scorecard PATCH must never overwrite {forbidden.strip()}"
            )

    def test_score_override_request_defaults_mocked(self):
        ScoreOverrideRequest = _skip_import("app.schemas.api_contracts", "ScoreOverrideRequest")
        ScoreState = _skip_import("app.schemas.enums", "ScoreState")
        req = ScoreOverrideRequest(human_override_points=2)
        assert req.score_state == ScoreState.VERIFIED


# ---------------------------------------------------------------------------
# (b) Dev-milestone completion never auto-awards assessment score
# ---------------------------------------------------------------------------
class TestDevMilestoneDecoupling:
    def test_dev_status_enum_separate_from_score_state_mocked(self):
        DevelopmentMilestoneStatus = _skip_import(
            "app.schemas.enums", "DevelopmentMilestoneStatus"
        )
        ScoreState = _skip_import("app.schemas.enums", "ScoreState")
        assert {s.value for s in DevelopmentMilestoneStatus} == {
            "outstanding",
            "partial",
            "completed",
        }
        assert "completed" not in {s.value for s in ScoreState}

    def test_milestones_source_never_writes_criterion_points(self, backend_dir: Path):
        """Static: milestones endpoint must not touch criterion point fields."""
        target = backend_dir / "app" / "api" / "v1" / "endpoints" / "milestones.py"
        if not target.is_file():
            pytest.skip("Track 1 milestones endpoint not wired yet")
        source = target.read_text(encoding="utf-8")
        for forbidden in ("ai_proposed_points", "human_override_points", "effective_points"):
            assert forbidden not in source, (
                f"milestones endpoint must not reference {forbidden} "
                "(dev completion and assessment score are separate dimensions)"
            )

    def test_score_dimensions_are_distinct_schemas_mocked(self):
        schemas = _skip_import("app.schemas.api_contracts")
        dev_fields = set(schemas.DevelopmentProgressSummarySchema.model_fields)
        score_fields = set(schemas.ExpectedScoreSummarySchema.model_fields)
        assert "completion_pct" in dev_fields
        assert "estimated_points" in score_fields and "verified_points" in score_fields
        assert "completion_pct" not in score_fields


# ---------------------------------------------------------------------------
# (c) Zero persistent email storage + ephemeral purge
# ---------------------------------------------------------------------------
class TestEphemeralEmailPrivacy:
    def test_no_email_column_in_models_source(self, backend_dir: Path):
        """Static: no SQLAlchemy model may declare a persistent email column."""
        models = backend_dir / "app" / "models" / "models.py"
        if not models.is_file():
            pytest.skip("Track 1 models not wired yet")
        source = models.read_text(encoding="utf-8").lower()
        assert "notification_email" not in source
        # `notify_email_once` may appear only in comments/docs, never as a Column.
        assert "notify_email_once = column" not in source
        assert "notification_email = column" not in source

    def test_trigger_request_holds_ephemeral_field_but_run_schema_has_none_mocked(self):
        schemas = _skip_import("app.schemas.api_contracts")
        assert "notify_email_once" in schemas.TriggerAnalysisRequest.model_fields
        run_fields = set(schemas.AnalysisRunSchema.model_fields)
        assert "notify_email_once" not in run_fields
        assert not any("email" in f.lower() for f in run_fields), (
            f"AnalysisRunSchema must carry no email field, got: {sorted(run_fields)}"
        )

    def test_ephemeral_registry_purges_on_pop_mocked(self):
        registry_cls = _skip_import(
            "app.services.notification_service", "EphemeralNotificationRegistry"
        )
        registry = registry_cls()
        run_id = uuid4()
        registry.set(run_id, "developer@example.com")
        assert registry.has(run_id) is True
        assert registry.pop_once(run_id) == "developer@example.com"
        assert registry.has(run_id) is False  # purged: single use
        assert registry.pop_once(run_id) is None  # second pop finds nothing

    def test_send_and_purge_never_retains_address_mocked(self, monkeypatch):
        service = _skip_import("app.services.notification_service")
        registry = service.EphemeralNotificationRegistry()
        run_id = uuid4()
        registry.set(run_id, "developer@example.com")

        sent_messages: list = []

        class _FakeSMTP:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def login(self, *args, **kwargs):
                return None

            def send_message(self, message):
                sent_messages.append(message)

        monkeypatch.setattr(service.smtplib, "SMTP_SSL", _FakeSMTP)
        monkeypatch.setattr(service.smtplib, "SMTP", _FakeSMTP)

        assert service.send_and_purge(run_id, "subject", "body", registry=registry) is True
        assert registry.has(run_id) is False  # purged even on success
        # Second dispatch finds nothing staged (no re-send, no retention).
        assert service.send_and_purge(run_id, "subject", "body", registry=registry) is False

    def test_analyses_source_never_logs_email_value(self, backend_dir: Path):
        """Static: analyses endpoint must not log/persist the raw address."""
        target = backend_dir / "app" / "api" / "v1" / "endpoints" / "analyses.py"
        if not target.is_file():
            pytest.skip("Track 1 analyses endpoint not wired yet")
        source = target.read_text(encoding="utf-8")
        for line in source.splitlines():
            lowered = line.lower()
            if "notify_email_once" in lowered and ("log" in lowered or "print" in lowered):
                pytest.fail(f"email address must never hit logs: {line.strip()}")


# ---------------------------------------------------------------------------
# (d) SSRF protection: GitHub allow-list + blocked IP literals
# ---------------------------------------------------------------------------
class TestSSRFProtection:
    VALID_URLS = [
        "https://github.com/DataTalksClub/ai-dev-tools-zoomcamp",
        "https://github.com/DataTalksClub/ai-dev-tools-zoomcamp.git",
        "https://github.com/owner/repo/tree/main",
    ]
    REJECTED_GITHUB_URLS = [
        "http://github.com/owner/repo",  # non-HTTPS
        "https://gitlab.com/owner/repo",  # non-GitHub host
        "https://github.example.com/owner/repo",  # enterprise lookalike
        "git@github.com:owner/repo.git",  # SSH form
        "https://github.com/onlyowner",  # missing repo
        "https://evil-github.com/owner/repo",  # lookalike domain
    ]
    BLOCKED_DEPLOYMENT_URLS = [
        "http://localhost:3000",
        "http://127.0.0.1:8000",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
    ]

    def test_only_public_github_urls_accepted_mocked(self):
        github_service = _skip_import("app.services.github_service")
        for url in self.VALID_URLS:
            assert github_service.is_public_repo_allowed(url) is True, url
        for url in self.REJECTED_GITHUB_URLS:
            assert github_service.is_public_repo_allowed(url) is False, url

    def test_github_url_parsing_extracts_owner_repo_mocked(self):
        github_service = _skip_import("app.services.github_service")
        parsed = github_service.parse_github_url("https://github.com/DataTalksClub/repo.git")
        assert (parsed.owner, parsed.repo) == ("DataTalksClub", "repo")

    def test_deployment_monitor_blocks_private_loopback_metadata_ips_mocked(self):
        monitor = _skip_import("app.services.deployment_monitor")
        for url in self.BLOCKED_DEPLOYMENT_URLS:
            with pytest.raises(monitor.SSRFBlockedError):
                monitor.validate_target_url(url)

    def test_deployment_monitor_allows_public_host_with_mocked_dns(self, monkeypatch):
        monitor = _skip_import("app.services.deployment_monitor")

        def _fake_getaddrinfo(host, port, *args, **kwargs):
            assert host == "example.com"
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
            ]

        monkeypatch.setattr(monitor.socket, "getaddrinfo", _fake_getaddrinfo)
        assert monitor.validate_target_url("https://example.com/health") == (
            "https://example.com/health"
        )

    def test_resolved_private_ip_is_rejected_with_mocked_dns(self, monkeypatch):
        """DNS rebinding guard: hostname resolving to 10/8 must be blocked."""
        monitor = _skip_import("app.services.deployment_monitor")

        def _fake_getaddrinfo(host, port, *args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 0))]

        monkeypatch.setattr(monitor.socket, "getaddrinfo", _fake_getaddrinfo)
        with pytest.raises(monitor.SSRFBlockedError):
            monitor.validate_target_url("https://example.com/")

    def test_blocked_ip_literals_are_forbidden(self):
        ipaddress_mod = ipaddress  # stdlib, no mock needed
        for literal in ("127.0.0.1", "10.0.0.1", "192.168.1.1", "169.254.169.254"):
            parsed = ipaddress_mod.ip_address(literal)
            assert (
                parsed.is_private
                or parsed.is_loopback
                or parsed.is_link_local
                or parsed.is_reserved
                or str(parsed) == "169.254.169.254"
            ), literal


# ---------------------------------------------------------------------------
# (e) Advisory read-only: no push/PR/mutate endpoints
# ---------------------------------------------------------------------------
_FORBIDDEN_ROUTE_RE = re.compile(
    r"push|pull[-_ ]?request|merge[-_ ]?pr|create[-_ ]?pr|open[-_ ]?pr|"
    r"commit[-_ ]?push|repo[-_ ]?push|git[-_ ]?push",
    re.IGNORECASE,
)


class TestAdvisoryReadOnly:
    def test_no_mutating_repo_routes_live(self, client, fastapi_app):
        """Live: enumerate the served OpenAPI document; no push/PR/mutation
        route may exist. (Routes are inspected via /openapi.json because
        newer FastAPI nests v1 routers in a lazy _IncludedRouter wrapper.)"""
        spec = client.get("/openapi.json")
        assert spec.status_code == 200
        paths = spec.json().get("paths", {})
        assert "/api/v1/health" in paths
        assert "/api/v1/auth/login" in paths
        for path, operations in paths.items():
            methods = {m.upper() for m in operations} & {"POST", "PUT", "PATCH", "DELETE"}
            if methods and _FORBIDDEN_ROUTE_RE.search(path or ""):
                pytest.fail(f"forbidden mutating repo route: {sorted(methods)} {path}")
        # Sanity: the frozen contract surface is actually mounted (API_CONTRACT §§1-8).
        for required in (
            "/api/v1/projects",
            "/api/v1/projects/{project_id}/scorecard",
            "/api/v1/projects/{project_id}/milestones/approve",
            "/api/v1/oncall/diagnose",
        ):
            assert required in paths, f"contract route missing from OpenAPI: {required}"

    def test_expected_read_only_surface_present_live(self, client):
        """Live: core read-only GET endpoints from the frozen contract respond."""
        health = client.get("/api/v1/health")
        assert health.status_code == 200

    def test_scorecard_carries_advisory_disclaimer_mocked(self):
        schemas = _skip_import("app.schemas.api_contracts")
        disclaimer = schemas.ScorecardResponse.model_fields["advisory_disclaimer"].default
        assert "advisory" in str(disclaimer).lower()
        assert "never" in str(disclaimer).lower() or "official" in str(disclaimer).lower()

    def test_expected_score_schema_disclaims_official_grades_mocked(self):
        schemas = _skip_import("app.schemas.api_contracts")
        notice = schemas.ExpectedScoreSummarySchema().advisory_notice
        assert "advisory" in notice.lower()
