# DevTrack AI — Product Specification v0.3

**Tagline:** Your AI mentor from project idea to deployment.

**Product positioning:** Course-first AI project mentor, initially targeting DataTalksClub Zoomcamp participants.

**Primary objective:** Help developers complete technical course projects by tracking requirements, analysing implementation evidence, identifying blockers, evaluating security and deployment, and estimating their expected course score.

## 1. Product vision

DevTrack AI accompanies developers throughout their project lifecycle.

It compares actual repository implementation against course requirements and provides evidence-based recommendations.

It should answer:

1. Am I meeting the course requirements?
2. How many points could my project currently receive?
3. What is preventing me from receiving more points?
4. What should I work on next?
5. Is my application secure and successfully deployed?

The application is advisory and read-only. It does not automatically modify repositories.

## 2. Target audience

- DataTalksClub Zoomcamp participants.
- Developers completing technical assignments.
- Students building portfolio projects.
- Developers managing multiple educational projects.

Initial focus: AI Dev Tools Zoomcamp and other technical courses.

The underlying architecture should support different course rubrics.

## 3. User management

- One predefined account.
- Login credentials documented in README for reviewers.
- No public registration.
- Multiple projects per account.
- Public GitHub repositories only.
- Projects can be active, paused, archived or completed.

## 4. Project configuration

Each project contains:

- Project name and description.
- Public GitHub repository URL.
- Course name.
- Rubric source (URL, uploaded document or pasted text).
- Start and target dates.
- Weekly time commitment.
- Generated assessment milestones.
- Optional diary file or directory.
- Deployment URL.
- Daily analysis schedule.

## 5. Rubric-driven project planning

The user provides course requirements.

Supported inputs:
- Public URLs.
- PDF documents.
- Markdown.
- Plain text.

The AI extracts:
- Assessment criteria.
- Point values.
- Scoring levels.
- Acceptance criteria.
- Required evidence.
- Passing threshold, where specified.

Generated milestones must be approved before becoming active.

The original rubric, source URL, version and retrieval date must be retained.

The system must distinguish official scoring criteria from AI-generated recommendations.

## 6. Official AI Dev Tools Zoomcamp scorecard

Initial built-in rubric: DataTalksClub AI Dev Tools Zoomcamp 2026.

Source: https://github.com/DataTalksClub/ai-dev-tools-zoomcamp/tree/main/project

The current published rubric contains 12 criteria, 24 maximum points and a passing threshold of 10 points.

| Assessment criterion | Maximum |
|---|---:|
| Problem Description | 2 |
| Product Specification | 2 |
| Agent Team Specification | 2 |
| Context Management | 2 |
| Application | 2 |
| Testing | 2 |
| Containerization | 2 |
| Deployment | 2 |
| CI/CD | 3 |
| Observability | 2 |
| Alerting on User Impact | 1 |
| On-Call Agent | 2 |
| **Total** | **24** |

Passing threshold: 10/24.

### Official scoring levels

Each criterion follows its published scoring descriptions.

For example:

**CI/CD (0–3 points)**

- 0: No CI/CD pipeline.
- 1: CI automatically runs tests on every pull request.
- 2: CI runs tests and CD deploys automatically.
- 3: CI runs tests, CD deploys to development, and production deployment is manual.

**Application (0–2 points)**

- 0: No working application, or a missing frontend, backend or persistent storage.
- 1: Frontend, backend and database exist but are not fully connected.
- 2: Full-stack application works end-to-end and runs locally with a single command.

All remaining criteria must similarly use the official descriptions, not invented scoring rules.

The rubric must be versioned so changes in future cohorts do not silently modify existing project assessments.

### Score states

Each assessment has one of three states:

- Estimated: AI has proposed a score based on available evidence.
- Verified: Supporting evidence has been checked.
- Needs review: Evidence is incomplete or ambiguous.

Human reviewers can override proposed scores.

The original AI score and reasoning must remain available for comparison.

## 7. Development milestones versus assessment milestones

Two separate milestone levels are required.

**Assessment milestones**

Represent official course criteria and their point values.

**Development milestones**

Represent actionable implementation tasks associated with assessment criteria.

Example:

CI/CD (maximum 3 points):
- Configure GitHub Actions.
- Run automated tests on pull requests.
- Configure automatic development deployment.
- Implement controlled production promotion.

Multiple development tasks can contribute to one assessment criterion.

Subtask completion must not automatically determine the official score.

## 8. Progress evaluation

Progress is measured in two separate dimensions:

**Development completion**
- Completed tasks.
- Partially completed tasks.
- Outstanding tasks.
- Deadline adherence.

**Expected course score**
- Estimated points.
- Verified points.
- Potential additional points.
- Remaining assessment gaps.

The application must never present an AI estimate as an official grade.

## 9. Main application modules

### Project dashboard
- Multiple active projects.
- Development progress.
- Expected course score.
- Upcoming deadlines.
- Last analysis.
- Security status.
- Deployment status.

### AI project mentor
- Evaluate implementation against course requirements.
- Identify missing functionality.
- Detect stalled development and scope creep.
- Compare repository evidence with previous snapshots.
- Recommend next development actions.

### Rubric scorecard
- Display all assessment criteria.
- Show maximum and estimated points.
- Link findings to supporting evidence.
- Track scoring history.
- Identify opportunities for additional points.

### Evidence explorer
Evidence can include:
- Git commits and source files.
- README and documentation.
- GitHub Actions workflows.
- Test results.
- Deployment URLs.
- Observability configuration.
- Security scanner reports.

### Development diary analyst
Automatically discover common diary files, with manual path override.

Extract completed work, blockers, decisions and next steps.

Compare diary entries with Git history and actual implementation.

### Security reviewer
Use deterministic scanners:
- Semgrep.
- Gitleaks.
- pip-audit.
- npm audit.
- Bandit where applicable.

Gemini explains and prioritizes findings.

### Deployment monitor
- Discover deployment URLs from README and configuration.
- Allow manual URL entry.
- Monitor websites and API health endpoints.
- Check HTTP status, HTTPS and response time.
- Maintain availability history.

## 10. Daily and manual analysis

Every active project receives daily automated analysis.

Manual re-analysis is available at any time.

Initial analysis:
- Broad repository inspection.
- Rubric evaluation.
- Diary discovery.
- Security baseline.
- Deployment discovery.

Subsequent analyses:
- New commits.
- Changed files.
- Diary updates.
- Security changes.
- Deployment status.
- Milestone reassessment.

Save every analysis with the corresponding repository commit SHA.

## 11. Recommendations and prioritization

Recommendations should include:
- Suggested task.
- Related assessment criterion.
- Potential points affected.
- Priority.
- Supporting evidence.
- Estimated effort where possible.

Prioritization should consider:
- Deadline proximity.
- Missing assessment points.
- Implementation dependencies.
- Estimated effort.
- Technical risk.

The application should identify high-value tasks rather than merely suggesting more development.

## 12. Notifications

Optional one-time email notifications.

- No permanent subscriptions.
- No persistent email storage.
- Temporary in-memory address while the job is pending.
- No email addresses in logs or analytics.
- Explicit disclosure that the address is used once.

Pending notifications may be lost following a server restart.

## 13. Technical architecture

| Component | Technology |
|---|---|
| Frontend | React + TypeScript |
| Backend | FastAPI |
| API contract | OpenAPI |
| Database | PostgreSQL |
| ORM | SQLAlchemy |
| Background jobs | PostgreSQL-backed worker |
| LLM | Gemini |
| GitHub | REST API and Git |
| Security | Semgrep, Gitleaks, pip-audit |
| HTTP monitoring | HTTPX |
| Tests | Pytest + Playwright |
| Deployment | Docker Compose + Nginx |

Backend modules:
- Authentication.
- Projects.
- Rubric processing.
- Assessment scoring.
- Evidence collection.
- GitHub integration.
- Diary analysis.
- Progress evaluation.
- Security scanning.
- Deployment monitoring.
- Notifications.
- AI orchestration.

## 14. Agent architecture

Initial specialized agents:

- Project Mentor / Orchestrator.
- Rubric Analyst.
- Progress Analyst.
- Diary Analyst.
- Security Reviewer.

Deployment and repository inspection remain deterministic services initially.

Agent instructions and skills use the existing agents_template as their foundation.

All agents must provide structured outputs, evidence references and uncertainty where appropriate.

## 15. Security requirements

- Public repositories only.
- Read-only GitHub access.
- No arbitrary repository script execution on production.
- Isolated scanning environments.
- SSRF protection for deployment monitoring.
- Secret protection.
- Resource limits for analysis jobs.
- HTTPS.
- No sensitive data in telemetry.

## 16. Infrastructure

Initial hosting:
- Existing Linux VPS.
- 4 GB RAM.
- 120 GB SSD.
- Docker Compose.
- PostgreSQL.
- Separate backend and worker processes.
- HTTPS reverse proxy.
- Persistent report storage.
- Automated backups.

Gemini provides external inference.

## 17. Development phases

### Phase 1 — Foundation
- Authentication.
- Project management.
- Public GitHub integration.
- Rubric ingestion.
- Official AI Dev Tools scorecard.
- AI-generated milestones.
- Evidence model.
- Dashboard.

### Phase 2 — Project intelligence
- Repository analysis.
- Git history.
- Diary discovery.
- Milestone evaluation.
- AI recommendations.
- Daily scheduling.
- Manual analysis.
- Historical snapshots.

### Phase 3 — Security and deployment
- Security scanners.
- Finding explanations.
- Deployment discovery.
- HTTP monitoring.
- Email notifications.

### Phase 4 — Operations and agent capabilities
- CI/CD.
- VPS production deployment.
- OpenTelemetry.
- Prometheus, Loki, Tempo and Grafana.
- Actionable alerts.
- Bounded read-only on-call agent.
- Reusable skills and specialized subagents.
- Independent evaluation.

## 18. Future roadmap

- Additional Zoomcamp rubrics.
- Private GitHub repositories.
- GitHub PR integration.
- MCP server.
- Course-specific learning recommendations.
- Completion reports.
- LLM comparison and recommendation evaluation.

## 19. Product success criteria

The application should demonstrate that it can:

1. Import public repositories.
2. Extract and version course requirements.
3. Generate editable assessment milestones.
4. Evaluate all 12 official AI Dev Tools criteria.
5. Propose scores supported by evidence.
6. Distinguish estimated from verified scores.
7. Track multiple projects.
8. Analyse progress daily and manually.
9. Interpret development diaries.
10. Identify security findings.
11. Monitor deployment availability.
12. Generate prioritized recommendations.
13. Maintain historical progress and scoring snapshots.
14. Send one-time notifications without persistent email storage.

**Product principle:** DevTrack AI should help developers maximize the quality of their projects and successfully complete course requirements, not merely report repository activity.

