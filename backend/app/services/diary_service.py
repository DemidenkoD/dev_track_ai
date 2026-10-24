"""Developer diary discovery + bounded read (Track 3).

Searches a checked-out repository for common diary locations or honors an
explicit manual override (``projects.diary_path``). Reads are size-capped so
a pathological markdown file cannot exhaust worker memory.

Public API:
    - :data:`DIARY_CANDIDATES`
    - :func:`discover_diary`
    - :func:`read_diary_bounded`
    - :func:`discover_and_read`
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

#: Ordered discovery candidates (relative to the repo root).
DIARY_CANDIDATES: tuple[str, ...] = (
    "DIARY.md",
    "docs/DIARY.md",
    "docs/diary.md",
    "NOTES.md",
    "DEVLOG.md",
    "journal.md",
)

#: Glob fallbacks searched when no literal candidate exists.
DIARY_GLOBS: tuple[str, ...] = ("journal/*.md", "docs/journal/*.md")

#: Safety caps for diary ingestion.
MAX_DIARY_BYTES = 100_000
MAX_EXCERPT_CHARS = 20_000


@dataclass
class DiaryRead:
    """Discovered diary path (repo-relative) plus a bounded excerpt."""

    discovered_path: str | None
    content_excerpt: str
    truncated: bool
    total_bytes: int


def _is_safe_relative(path_str: str) -> bool:
    """Reject absolute paths and parent-directory escapes for overrides."""
    p = Path(path_str)
    if p.is_absolute():
        return False
    return ".." not in p.parts


def discover_diary(
    repo_dir: str | Path, manual_override: str | None = None
) -> str | None:
    """Discover the diary file, returning a repo-relative path or None.

    Args:
        repo_dir: Root of the (shallow-cloned) repository checkout.
        manual_override: Explicit ``projects.diary_path`` value. When set and
            safe, it wins over auto-discovery. Unsafe overrides are ignored.

    Returns:
        Repo-relative POSIX path (e.g. ``"docs/DIARY.md"``) or None when no
        diary file exists.
    """
    root = Path(repo_dir)
    if manual_override:
        override = manual_override.strip()
        if override and _is_safe_relative(override):
            candidate = root / override
            if candidate.is_file():
                return override
            # Manual override points at a missing file: report as not found
            # rather than silently falling back (caller surfaces this).
            return None
        if override and not _is_safe_relative(override):
            return None  # unsafe override: never escape the checkout
    for candidate in DIARY_CANDIDATES:
        if (root / candidate).is_file():
            return candidate
    for pattern in DIARY_GLOBS:
        matches = sorted(root.glob(pattern))
        for match in matches:
            if match.is_file():
                return match.relative_to(root).as_posix()
    return None


def read_diary_bounded(path: str | Path, *, max_bytes: int = MAX_DIARY_BYTES) -> DiaryRead:
    """Read a diary file with a hard byte cap; never loads unbounded content.

    Args:
        path: Absolute path to the diary markdown file.
        max_bytes: Maximum bytes to read from disk.

    Returns:
        :class:`DiaryRead` with a UTF-8 excerpt (replacement chars on
        decode errors) and truncation metadata.
    """
    full = Path(path)
    try:
        total_bytes = full.stat().st_size
    except OSError:
        return DiaryRead(
            discovered_path=full.name, content_excerpt="", truncated=False, total_bytes=0
        )
    try:
        with open(full, "rb") as fh:
            raw = fh.read(max_bytes + 1)
    except OSError:
        return DiaryRead(
            discovered_path=full.name, content_excerpt="", truncated=False, total_bytes=total_bytes
        )
    truncated = len(raw) > max_bytes
    text = raw[:max_bytes].decode("utf-8", errors="replace")
    excerpt = text[:MAX_EXCERPT_CHARS]
    if len(text) > MAX_EXCERPT_CHARS:
        truncated = True
    return DiaryRead(
        discovered_path=full.name,
        content_excerpt=excerpt,
        truncated=truncated,
        total_bytes=total_bytes,
    )


def discover_and_read(
    repo_dir: str | Path,
    manual_override: str | None = None,
    *,
    max_bytes: int = MAX_DIARY_BYTES,
) -> DiaryRead:
    """Discover the diary in ``repo_dir`` and return its bounded excerpt.

    Combines :func:`discover_diary` and :func:`read_diary_bounded` so the
    analysis pipeline needs a single call. Returns an empty excerpt with
    ``discovered_path=None`` when no diary exists.
    """
    root = Path(repo_dir)
    found = discover_diary(root, manual_override=manual_override)
    if found is None:
        return DiaryRead(
            discovered_path=None, content_excerpt="", truncated=False, total_bytes=0
        )
    result = read_diary_bounded(root / found, max_bytes=max_bytes)
    result.discovered_path = found  # repo-relative path, not just basename
    return result
