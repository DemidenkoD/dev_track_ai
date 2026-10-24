"""Track 3 background worker package.

Polls the PostgreSQL-backed ``analysis_runs`` queue with
``SELECT ... FOR UPDATE SKIP LOCKED`` and schedules daily analyses for
active projects. See :mod:`app.worker.runner` for the entry points.
"""

from __future__ import annotations
