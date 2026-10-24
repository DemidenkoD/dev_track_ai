# Problem Description: The Course Project Blind Spot

## 1. The Core Problem

Developers and students participating in intensive technical cohorts—such as the **DataTalksClub Zoomcamps**—build end-to-end engineering projects over several weeks. While course organizers publish detailed grading rubrics (covering problem formulation, architecture, testing, containerization, CI/CD, observability, and AI agent integration), participants consistently struggle with five recurring failure modes:

1. **Rubric Misalignment & Hidden Gaps:** Developers spend days polishing features that yield zero additional rubric points while overlooking foundational criteria (e.g., missing a single-command startup, omitting PR test triggers in CI/CD, or failing to version agent skills) that cost them passing points.
2. **Subjective Self-Assessment vs. Hard Evidence:** Students assume they meet a criterion based on intent rather than verifiable repository evidence (commits, workflow runs, test coverage, OpenTelemetry spans, or documentation sections).
3. **Stalled Momentum & Scope Creep:** Without structured checkpoints linking daily coding tasks to specific rubric criteria, projects suffer from scope creep early on and panic-driven shortcuts right before the submission deadline.
4. **Unnoticed Security & Deployment Regressions:** Exposed secrets, vulnerable dependencies, broken health endpoints, or expired HTTPS certificates often go undetected until peer review or grading day, resulting in immediate point deductions or failed evaluations.
5. **Fragmented Project Tracking:** Course requirements live in GitHub markdown pages, implementation lives in Git commits and branches, personal reflections live in scattered development diaries, and live health lives on a remote VPS—with no unified mentor synthesizing them.

## 2. Why Existing Tools Fall Short

- **Generic Coding Assistants (Copilot, Cursor, ChatGPT):** Excel at writing code snippets or debugging isolated files, but lack persistent awareness of an external course rubric, multi-week milestone progression, historical commit snapshots, and live deployment/security state.
- **CI Linters & Security Scanners (GitHub Actions, Dependabot, Semgrep):** Produce raw technical logs and CVE lists without explaining how findings impact project readiness or prioritizing fixes relative to course deadlines and point values.
- **Task Trackers (Jira, Linear, Notion, GitHub Projects):** Require manual status updates and cannot autonomously verify whether a checked-off task is actually backed by working code, tests, and configurations in the repository.

## 3. How DevTrack AI Solves It

**DevTrack AI** is an **advisory, read-only AI project mentor** purpose-built for technical course participants. Rather than modifying code automatically, it continuously inspects a public GitHub repository, development diary, security posture, and live deployment against a versioned course rubric to answer five critical questions at any moment:

1. **Am I meeting the course requirements?** (Rubric Scorecard mapped to concrete file/commit evidence)
2. **How many points could my project currently receive?** (Explicit distinction between *Estimated*, *Verified*, and *Needs Review* scores, never masquerading as an official grade)
3. **What is preventing me from receiving more points?** (Gap analysis separating *Assessment Milestones* from actionable *Development Milestones*)
4. **What should I work on next?** (High-ROI recommendations prioritized by missing rubric points, deadline proximity, dependencies, and technical risk)
5. **Is my application secure and successfully deployed?** (Deterministic scanning with Semgrep, Gitleaks, `pip-audit`, `npm audit`, and Bandit paired with Gemini explanations, plus SSRF-safe HTTP/HTTPS deployment monitoring)

## 4. Target Users & Impact

- **Primary Users:** DataTalksClub AI Dev Tools Zoomcamp participants (and broader Zoomcamp cohorts).
- **Secondary Users:** Independent learners building portfolio projects and cohort reviewers verifying submission evidence.
- **Measurable Outcome:** Higher project completion rates, elimination of avoidable rubric blind spots, zero leaked secrets at submission time, and transparent, evidence-backed self-assessment prior to peer grading.

