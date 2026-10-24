"""Track 3 deterministic inspection services (read-only, advisory only).

This package never pushes commits, opens PRs, or modifies user repositories.
It only inspects public ``https://github.com/<owner>/<repo>`` URLs, runs
static scanners in isolated subprocesses, performs SSRF-guarded HTTP checks,
and holds one-time notification emails strictly in volatile memory.
"""

from __future__ import annotations
