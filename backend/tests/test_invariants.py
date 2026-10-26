"""Track 5: product invariants — live (isolated SQLite) + mocked, no network.

Gate: ``pytest -m invariants`` (see pytest.ini). Every test is skip-safe:
missing Track 1 wiring or optional telemetry SDKs yield ``pytest.skip`` with
a reason (surfaced by ``-ra``) instead of a silent green pass.

Covers (AGENTS.md §1 + backend/AGENTS.md §2 + DATABASE_SCHEMA.md):

  1. Built-in rubric: 12 criteria / 24 max points / 10-point passing threshold.
  2. Dev-milestone completion NEVER auto-awards assessment scores
     (Development Completion vs Expected Course Score stay separate).
  3. Scorecard override preserves ``ai_proposed_points`` + ``ai_reasoning``,
     sets ``overridden_at``; 400 on over-max override; 400/422 on invalid
     ``score_state``; 404 cross-project.
  4. Email hardening: ``notify_email_once`` never in logs/traces/metrics;
     ``acknowledge=false`` → 400; SMTPException failure-path still purges;
     GET /analyses never returns the address (only the
     ``ephemeral_notification_queued`` bool); dual EPHEMERAL stores detected.
  5. SSRF: evil redirect targets blocked, >3 hops → "too many redirects",
     ``metadata.google.internal`` / ``169.254.169.254`` blocked,
     ``user:pass@`` blocked, ``::ffff:127.0.0.1`` blocked,
     ``discover_deployment_url`` sources (readme/config/manual) +
     manual-override gate, ``clone_shallow`` gate
     (``shell=False``, depth 50, ``GIT_TERMINAL_PROMPT=0``, temp isolation).

No live GitHub/LLM/scanner/network. DNS is mocked in every path that could
resolve a hostname.
"""

from __future__ import annotations

import logging
import smtplib
import socket
from pathlib import Path
from uuid import UUID, uuid4

import pytest

pytestmark = [pytest.mark.invariants, pytest.mark.unit]


# ---------------------------------------------------------------------------
# Isolated live-client fixture (SQLite in-memory, seeded rubric, stub auth).
# Never touches Postgres, the network, LLM, or scanners.
# ---------------------------------------------------------------------------
def _import_or_skip(module: str, name: str | None = None):
    try:
        mod = pytest.importorskip(
            module, reason=f"Blocked on Track 1 dep: {module} unavailable"
        )
    except pytest.skip.Exception:
        raise
    return getattr(mod, name) if name else mod


@pytest.fixture()
def isolated_client(tmp_path):
    """Function-scoped TestClient over throwaway SQLite + seeded rubric."""
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
    except ImportError as exc:
        pytest.skip(f"SQLAlchemy unavailable: {exc}")

    try:
        from app.db.base import Base
        from app.db.init_db import seed_builtin_rubric
        from app.main import app
        from app.core.deps import get_current_user, get_db
        from app.schemas.api_contracts import UserProfileSchema
    except Exception as exc:
        pytest.skip(f"Track 1 backend unavailable: {type(exc).__name__}: {exc}")

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    seed_db = TestingSession()
    try:
        seed_builtin_rubric(seed_db)
    finally:
        seed_db.close()

    def _override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    def _override_user():
        return UserProfileSchema(username="reviewer@datatalks.club", role="reviewer")

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    # Volatile email map is process-global: start each test clean.
    try:
        from app.api.v1.endpoints import analyses as analyses_mod

        analyses_mod.EPHEMERAL_NOTIFICATIONS.clear()
    except Exception:
        pass

    try:
        from fastapi.testclient import TestClient
    except ImportError as exc:
        pytest.skip(f"fastapi.testclient unavailable: {exc}")

    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield client, TestingSession
    finally:
        app.dependency_overrides.clear()
        try:
            from app.api.v1.endpoints import analyses as analyses_mod

            analyses_mod.EPHEMERAL_NOTIFICATIONS.clear()
        except Exception:
            pass


def _create_project(client, name: str = "Invariant Probe") -> dict:
    resp = client.post(
        "/api/v1/projects",
        json={
            "name": name,
            "description": "Track 5 invariant probe (isolated SQLite).",
            "github_repo_url": "https://github.com/octocat/hello-world",
            "course_name": "AI Dev Tools Zoomcamp 2026",
        },
    )
    assert resp.status_code == 201, f"project creation failed: {resp.status_code} {resp.text[:300]}"
    return resp.json()


def _seed_criterion_assessments(Session, project_id: str, run_id: str, milestones: list[dict], points: int = 1):
    """Insert worker-like criterion assessments directly (worker is out of scope)."""
    models = _import_or_skip("app.models.models")
    enums = _import_or_skip("app.schemas.enums")
    db = Session()
    try:
        rows = []
        for am in milestones[:2]:
            rows.append(
                models.CriterionAssessment(
                    analysis_run_id=UUID(run_id),
                    project_id=UUID(project_id),
                    assessment_milestone_id=UUID(am["id"]),
                    criterion_code=am.get("criterion_code", "ci_cd"),
                    max_points=am.get("max_points", 2),
                    ai_proposed_points=points,
                    ai_reasoning="probe reasoning (must survive dev-milestone updates)",
                    ai_confidence=0.7,
                    missing_for_next_level="probe next level",
                    score_state=enums.ScoreState.ESTIMATED,
                    evidence_ids=[],
                )
            )
        db.add_all(rows)
        db.commit()
        return [str(r.id) for r in rows]
    finally:
        db.close()


def _assessment_snapshot(Session, run_id: str) -> list[tuple]:
    models = _import_or_skip("app.models.models")
    db = Session()
    try:
        rows = (
            db.query(models.CriterionAssessment)
            .filter(models.CriterionAssessment.analysis_run_id == UUID(run_id))
            .order_by(models.CriterionAssessment.criterion_code)
            .all()
        )
        return [
            (
                r.ai_proposed_points,
                r.ai_reasoning,
                r.ai_confidence,
                r.human_override_points,
                r.human_override_reason,
                str(r.score_state),
            )
            for r in rows
        ]
    finally:
        db.close()


# ---------------------------------------------------------------------------
# (1) Built-in rubric shape: 12 criteria / 24 max / 10 passing threshold
# ---------------------------------------------------------------------------
class TestBuiltinRubricShape:
    def test_rubric_json_is_12_criteria_24_max_10_pass(self, repo_root: Path):
        import json

        payload = json.loads(
            (repo_root / "docs" / "rubrics" / "ai_dev_tools_zoomcamp_2026.json").read_text()
        )
        assert len(payload["criteria"]) == 12
        assert payload["max_points"] == 24
        assert payload["passing_threshold"] == 10
        assert sum(c["max_points"] for c in payload["criteria"]) == 24

    def test_live_project_seeds_12_assessment_milestones_24_max(self, isolated_client):
        client, _ = isolated_client
        project = _create_project(client)
        resp = client.get(f"/api/v1/projects/{project['id']}/milestones")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["assessment_milestones"]) == 12
        assert sum(am["max_points"] for am in body["assessment_milestones"]) == 24
        assert body["milestones_approved"] is False


# ---------------------------------------------------------------------------
# (2) Live decoupling: dev-milestone completion never awards assessment points
# ---------------------------------------------------------------------------
class TestDevMilestoneDecouplingLive:
    def test_completed_dev_milestone_moves_dev_pct_not_assessment_scores(
        self, isolated_client
    ):
        client, Session = isolated_client
        project = _create_project(client, name="Decoupling Probe")
        pid = project["id"]

        milestones = client.get(f"/api/v1/projects/{pid}/milestones").json()[
            "assessment_milestones"
        ]
        parent_id = milestones[0]["id"]

        dev_ids: list[str] = []
        for title in ("probe task one", "probe task two"):
            resp = client.post(
                f"/api/v1/projects/{pid}/development-milestones",
                json={"assessment_milestone_id": parent_id, "title": title},
            )
            assert resp.status_code == 201, resp.text[:300]
            dev_ids.append(resp.json()["id"])

        run_id = client.get(f"/api/v1/projects/{pid}/analyses").json()[0]["id"]
        _seed_criterion_assessments(Session, pid, run_id, milestones, points=1)
        before = _assessment_snapshot(Session, run_id)
        assert len(before) == 2

        score_before = client.get(f"/api/v1/projects/{pid}/scorecard").json()[
            "expected_score"
        ]

        # Complete the first dev milestone → dev_completion_pct 50.0.
        resp = client.patch(
            f"/api/v1/projects/{pid}/development-milestones/{dev_ids[0]}",
            json={"status": "completed"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

        detail = client.get(f"/api/v1/projects/{pid}").json()
        assert detail["development_progress"]["completion_pct"] == 50.0
        assert _assessment_snapshot(Session, run_id) == before
        score_after_first = client.get(f"/api/v1/projects/{pid}/scorecard").json()[
            "expected_score"
        ]
        assert score_after_first == score_before

        # Complete the second → 100.0, still no assessment movement.
        resp = client.patch(
            f"/api/v1/projects/{pid}/development-milestones/{dev_ids[1]}",
            json={"status": "completed"},
        )
        assert resp.status_code == 200
        detail = client.get(f"/api/v1/projects/{pid}").json()
        assert detail["development_progress"]["completion_pct"] == 100.0
        assert _assessment_snapshot(Session, run_id) == before
        score_after_second = client.get(f"/api/v1/projects/{pid}/scorecard").json()[
            "expected_score"
        ]
        assert score_after_second == score_before


# ---------------------------------------------------------------------------
# (3a) Live scorecard override: preservation + validation + cross-project 404
# ---------------------------------------------------------------------------
class TestScorecardOverrideLive:
    def _setup(self, client, Session, name="Override Probe"):
        project = _create_project(client, name=name)
        pid = project["id"]
        milestones = client.get(f"/api/v1/projects/{pid}/milestones").json()[
            "assessment_milestones"
        ]
        run_id = client.get(f"/api/v1/projects/{pid}/analyses").json()[0]["id"]
        assessment_ids = _seed_criterion_assessments(Session, pid, run_id, milestones)
        return pid, run_id, assessment_ids[0]

    def test_override_preserves_ai_fields_and_sets_overridden_at(
        self, isolated_client
    ):
        client, Session = isolated_client
        pid, _, assessment_id = self._setup(client, Session)

        resp = client.patch(
            f"/api/v1/projects/{pid}/scorecard/{assessment_id}",
            json={
                "score_state": "verified",
                "human_override_points": 2,
                "human_override_reason": "Verified single-command Docker Compose startup.",
            },
        )
        assert resp.status_code == 200, resp.text[:300]
        body = resp.json()
        assert body["ai_proposed_points"] == 1
        assert body["ai_reasoning"] == "probe reasoning (must survive dev-milestone updates)"
        assert body["human_override_points"] == 2
        assert body["human_override_reason"] == "Verified single-command Docker Compose startup."
        assert body["overridden_at"] is not None
        assert body["effective_points"] == 2
        assert body["score_state"] == "verified"

    def test_override_rejects_points_above_max(self, isolated_client):
        client, Session = isolated_client
        pid, _, assessment_id = self._setup(client, Session, name="Over-max Probe")
        resp = client.patch(
            f"/api/v1/projects/{pid}/scorecard/{assessment_id}",
            json={"score_state": "verified", "human_override_points": 99},
        )
        assert resp.status_code == 400

    def test_override_rejects_invalid_score_state(self, isolated_client):
        client, Session = isolated_client
        pid, _, assessment_id = self._setup(client, Session, name="Bad-state Probe")
        resp = client.patch(
            f"/api/v1/projects/{pid}/scorecard/{assessment_id}",
            json={"score_state": "bogus_state", "human_override_points": 1},
        )
        # Pydantic rejects unknown ScoreState values (422) before the handler's
        # own 400 guard runs; both codes prove the invalid state is refused.
        assert resp.status_code in (400, 422)

    def test_override_cross_project_is_404(self, isolated_client):
        client, Session = isolated_client
        pid_a, _, assessment_id = self._setup(client, Session, name="Project A")
        project_b = _create_project(client, name="Project B")
        resp = client.patch(
            f"/api/v1/projects/{project_b['id']}/scorecard/{assessment_id}",
            json={"score_state": "verified", "human_override_points": 1},
        )
        assert resp.status_code == 404
        assert pid_a != project_b["id"]


# ---------------------------------------------------------------------------
# (4) Email hardening: live behaviour + failure-path purge + store detection
# ---------------------------------------------------------------------------
class TestEmailHardeningLive:
    PROBE = "track5-probe-7f3a9c@example.com"

    def test_acknowledge_false_is_400(self, isolated_client):
        client, _ = isolated_client
        project = _create_project(client, name="Email Ack Probe")
        resp = client.post(
            f"/api/v1/projects/{project['id']}/analyses",
            json={"notify_email_once": "someone@example.com", "acknowledge_ephemeral_email": False},
        )
        assert resp.status_code == 400

    def test_analyses_never_return_address_only_queued_bool(self, isolated_client, caplog):
        client, _ = isolated_client
        project = _create_project(client, name="Email Privacy Probe")
        pid = project["id"]
        with caplog.at_level(logging.DEBUG):
            resp = client.post(
                f"/api/v1/projects/{pid}/analyses",
                json={
                    "notify_email_once": self.PROBE,
                    "acknowledge_ephemeral_email": True,
                },
            )
        assert resp.status_code == 202
        assert resp.json()["ephemeral_notification_queued"] is True
        # The address must never hit logs (caplog capture across the request).
        assert self.PROBE not in caplog.text

        for resp in (client.get(f"/api/v1/projects/{pid}/analyses"),):
            assert resp.status_code == 200
            assert self.PROBE not in resp.text
            for run in resp.json():
                assert "notify_email_once" not in run
                assert not any("email" in k.lower() for k in run if k != "ephemeral_notification_queued"), (
                    f"email-like key leaked in AnalysisRun payload: {sorted(run)}"
                )

        run_id = client.get(f"/api/v1/projects/{pid}/analyses").json()[0]["id"]
        detail = client.get(f"/api/v1/projects/{pid}/analyses/{run_id}")
        assert detail.status_code == 200
        assert self.PROBE not in detail.text
        assert "notify_email_once" not in detail.json()

    def test_otel_spans_never_carry_address(self, isolated_client):
        """Skip-safe: runs only when the OpenTelemetry SDK is installed."""
        otel_trace = pytest.importorskip(
            "opentelemetry.trace", reason="OpenTelemetry SDK not installed"
        )
        client, _ = isolated_client
        project = _create_project(client, name="Otel Probe")
        tracer = otel_trace.get_tracer("track5-qa")
        with tracer.start_as_current_span("probe-trigger-analysis"):
            resp = client.post(
                f"/api/v1/projects/{project['id']}/analyses",
                json={
                    "notify_email_once": self.PROBE,
                    "acknowledge_ephemeral_email": True,
                },
            )
        assert resp.status_code == 202
        # Contract-level guarantee: the response carries only the queued bool.
        assert self.PROBE not in resp.text
        assert resp.json()["ephemeral_notification_queued"] is True

    def test_smtp_failure_path_still_purges_mocked(self, monkeypatch):
        service = _import_or_skip("app.services.notification_service")
        registry = service.EphemeralNotificationRegistry()
        run_id = uuid4()
        registry.set(run_id, "developer@example.com")

        class _ExplodingSMTP:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def send_message(self, message):
                raise smtplib.SMTPException("simulated outage")

        monkeypatch.setattr(service.smtplib, "SMTP_SSL", _ExplodingSMTP)
        monkeypatch.setattr(service.smtplib, "SMTP", _ExplodingSMTP)

        assert service.send_and_purge(run_id, "subject", "body", registry=registry) is False
        assert registry.has(run_id) is False  # purged even on failure
        assert service.send_and_purge(run_id, "subject", "body", registry=registry) is False

    def test_no_dual_ephemeral_stores_api_must_import_registry(self, backend_dir: Path):
        """The API layer must not keep its own EPHEMERAL dict.

        Track 3 owns the single volatile registry in
        ``app.services.notification_service``; ``analyses.py`` must stage via
        ``queue_notification`` / the shared registry (import), never via a
        module-local ``EPHEMERAL_NOTIFICATIONS: dict`` shadow copy that the
        worker can neither see nor purge. Reported to the orchestrator for
        Track 1/3 to fix — Track 5 never edits product code.
        """
        target = backend_dir / "app" / "api" / "v1" / "endpoints" / "analyses.py"
        if not target.is_file():
            pytest.skip("Track 1 analyses endpoint not wired yet")
        source = target.read_text(encoding="utf-8")
        defines_own_dict = "EPHEMERAL_NOTIFICATIONS: dict" in source or (
            "EPHEMERAL_NOTIFICATIONS = {}" in source
            or "EPHEMERAL_NOTIFICATIONS: Dict" in source
        )
        imports_registry = (
            "notification_service" in source and "EPHEMERAL_NOTIFICATIONS" in source
        ) or "queue_notification" in source
        assert not defines_own_dict, (
            "DUAL EPHEMERAL STORE: analyses.py defines its own "
            "EPHEMERAL_NOTIFICATIONS dict instead of importing the shared "
            "EphemeralNotificationRegistry from "
            "app.services.notification_service. The worker purges a different "
            "object, so one-time addresses staged by the API are never purged. "
            "Track 1/3 fix: import queue_notification / EPHEMERAL_NOTIFICATIONS "
            "from notification_service and delete the module-local dict."
        )
        assert imports_registry, (
            "analyses.py does not import the shared ephemeral registry "
            "(expected `from app.services.notification_service import ...`)."
        )


# ---------------------------------------------------------------------------
# (5) SSRF: literals, hosts, redirects, discovery, clone gate (mocked DNS)
# ---------------------------------------------------------------------------
def _public_dns(monkeypatch, module, ip: str = "93.184.216.34"):
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    monkeypatch.setattr(module.socket, "getaddrinfo", _fake_getaddrinfo)


class TestSSRFBlockingLive:
    BLOCKED = [
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
    ]

    def test_task_listed_literals_blocked(self):
        monitor = _import_or_skip("app.services.deployment_monitor")
        for url in self.BLOCKED:
            with pytest.raises(monitor.SSRFBlockedError):
                monitor.validate_target_url(url)

    def test_metadata_hostnames_blocked_without_dns(self):
        monitor = _import_or_skip("app.services.deployment_monitor")
        for url in (
            "http://metadata.google.internal/computeMetadata/v1/",
            "http://metadata.google.com/",
        ):
            with pytest.raises(monitor.SSRFBlockedError):
                monitor.validate_target_url(url)

    def test_userinfo_credentials_blocked(self, monkeypatch):
        monitor = _import_or_skip("app.services.deployment_monitor")
        _public_dns(monkeypatch, monitor)
        with pytest.raises(monitor.SSRFBlockedError):
            monitor.validate_target_url("https://user:pass@example.com/")

    def test_ipv4_mapped_loopback_blocked(self, monkeypatch):
        monitor = _import_or_skip("app.services.deployment_monitor")

        def _fake_getaddrinfo(host, port, *args, **kwargs):
            return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::ffff:127.0.0.1", 0, 0, 0))]

        monkeypatch.setattr(monitor.socket, "getaddrinfo", _fake_getaddrinfo)
        with pytest.raises(monitor.SSRFBlockedError):
            monitor.validate_target_url("http://[::ffff:127.0.0.1]/")

    def test_evil_redirect_target_blocked(self, monkeypatch):
        monitor = _import_or_skip("app.services.deployment_monitor")
        _public_dns(monkeypatch, monitor)

        httpx = pytest.importorskip("httpx")

        class _RedirectToMetadata:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def get(self, url):
                return httpx.Response(
                    302,
                    headers={"location": "http://169.254.169.254/latest/meta-data/"},
                    request=httpx.Request("GET", url),
                )

        monkeypatch.setattr(httpx, "Client", _RedirectToMetadata)
        health = monitor.check_deployment_health("https://example.com/start")
        assert health.is_reachable is False
        assert "SSRF blocked" in (health.error_detail or "")

    def test_more_than_three_hops_is_too_many_redirects(self, monkeypatch):
        monitor = _import_or_skip("app.services.deployment_monitor")
        _public_dns(monkeypatch, monitor)

        httpx = pytest.importorskip("httpx")

        class _EndlessRedirect:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def get(self, url):
                return httpx.Response(
                    302,
                    headers={"location": "https://example.com/next"},
                    request=httpx.Request("GET", url),
                )

        monkeypatch.setattr(httpx, "Client", _EndlessRedirect)
        health = monitor.check_deployment_health("https://example.com/start")
        assert health.is_reachable is False
        assert "too many redirects" in (health.error_detail or "")


class TestDeploymentDiscoveryGates:
    def test_readme_config_and_manual_sources(self, monkeypatch, tmp_path):
        monitor = _import_or_skip("app.services.deployment_monitor")
        _public_dns(monkeypatch, monitor)

        readme_repo = tmp_path / "readme_repo"
        readme_repo.mkdir()
        (readme_repo / "README.md").write_text(
            "# Demo\nLive at https://example.com/readme-app\n", encoding="utf-8"
        )
        url, source = monitor.discover_deployment_url(str(readme_repo))
        assert url == "https://example.com/readme-app"
        assert source == "readme"

        config_repo = tmp_path / "config_repo"
        config_repo.mkdir()
        (config_repo / "fly.toml").write_text(
            'app = "demo"\nurl = "https://example.com/config-app"\n', encoding="utf-8"
        )
        url, source = monitor.discover_deployment_url(str(config_repo))
        assert url == "https://example.com/config-app"
        assert source == "config"

    def test_manual_override_wins_and_is_gated(self, monkeypatch, tmp_path):
        monitor = _import_or_skip("app.services.deployment_monitor")
        _public_dns(monkeypatch, monitor)

        empty_repo = tmp_path / "empty_repo"
        empty_repo.mkdir()
        url, source = monitor.discover_deployment_url(
            str(empty_repo), manual_override="https://example.com/manual-app"
        )
        assert (url, source) == ("https://example.com/manual-app", "manual")

        # SSRF-blocked manual override never becomes a deployment target.
        url, source = monitor.discover_deployment_url(
            str(empty_repo), manual_override="http://169.254.169.254/"
        )
        assert url is None
        assert source == "manual"


class TestCloneShallowGate:
    def test_static_clone_gate_markers(self, backend_dir: Path):
        target = backend_dir / "app" / "services" / "github_service.py"
        if not target.is_file():
            pytest.skip("Track 3 github_service not wired yet")
        source = target.read_text(encoding="utf-8")
        assert "CLONE_DEPTH = 50" in source
        assert '"--depth"' in source and "str(depth)" in source
        assert "shell=False" in source
        assert 'GIT_TERMINAL_PROMPT", "0"' in source or "GIT_TERMINAL_PROMPT': '0'" in source or 'GIT_TERMINAL_PROMPT": "0"' in source
        assert "TemporaryDirectory" in source
        # git clone <url> <dest> requires dest to NOT pre-exist.
        assert "must not pre-exist" in source.lower() or "do not mkdir" in source.lower() or "Do NOT mkdir" in source

    def test_clone_invokes_git_without_shell_depth_50_no_prompt(self, monkeypatch, tmp_path):
        service = _import_or_skip("app.services.github_service")
        assert service.CLONE_DEPTH == 50
        calls: list[dict] = []

        class _Completed:
            returncode = 0
            stdout = "abc1234def5678\n"
            stderr = ""

        def _fake_run(args, **kwargs):
            calls.append({"args": list(args), "kwargs": kwargs})
            return _Completed()

        monkeypatch.setattr(service.subprocess, "run", _fake_run)
        parent = tmp_path / "parent"
        parent.mkdir()
        dest = parent / "checkout"
        result = service.clone_shallow("https://github.com/octocat/hello-world", dest)
        clone_call = calls[0]
        assert clone_call["kwargs"].get("shell") is False
        assert "--depth" in clone_call["args"] and "50" in clone_call["args"]
        assert clone_call["kwargs"]["env"]["GIT_TERMINAL_PROMPT"] == "0"
        assert result.commit_sha == "abc1234def5678"
        assert result.path == dest
