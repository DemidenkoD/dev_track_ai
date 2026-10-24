"""Domain enums shared across SQLAlchemy models, Pydantic REST schemas, and AI agents."""

from enum import StrEnum


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"
    COMPLETED = "completed"


class RubricSourceType(StrEnum):
    BUILTIN = "builtin"
    URL = "url"
    PDF = "pdf"
    MARKDOWN = "markdown"
    TEXT = "text"


class ScoreState(StrEnum):
    ESTIMATED = "estimated"
    VERIFIED = "verified"
    NEEDS_REVIEW = "needs_review"


class DevelopmentMilestoneStatus(StrEnum):
    OUTSTANDING = "outstanding"
    PARTIAL = "partial"
    COMPLETED = "completed"


class MilestoneSource(StrEnum):
    AI_GENERATED = "ai_generated"
    USER_CREATED = "user_created"


class AnalysisTriggerType(StrEnum):
    INITIAL = "initial"
    DAILY = "daily"
    MANUAL = "manual"


class AnalysisStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EvidenceType(StrEnum):
    COMMIT = "commit"
    SOURCE_FILE = "source_file"
    README = "readme"
    DOCUMENTATION = "documentation"
    CI_WORKFLOW = "ci_workflow"
    TEST_RESULT = "test_result"
    DOCKER_COMPOSE = "docker_compose"
    DEPLOYMENT_URL = "deployment_url"
    OBSERVABILITY_CONFIG = "observability_config"
    SECURITY_REPORT = "security_report"
    AGENT_CONFIG = "agent_config"
    DIARY_ENTRY = "diary_entry"


class SecurityStatus(StrEnum):
    PASS = "pass"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class SeverityLevel(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DeploymentDiscoverySource(StrEnum):
    README = "readme"
    CONFIG = "config"
    MANUAL = "manual"


class PriorityLevel(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

