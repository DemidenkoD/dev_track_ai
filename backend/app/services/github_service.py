"""Read-only GitHub inspector for public repositories (Track 3).

Advisory & read-only: this module never pushes commits, opens PRs, or
modifies user repositories. Only public ``https://github.com/<owner>/<repo>``
URLs are permitted. Cloned code is inspected statically — untrusted repo
code (setup scripts, Makefiles, hooks) is never executed.

Public API:
    - :func:`parse_github_url`
    - :func:`is_public_repo_allowed`
    - :func:`fetch_repo_metadata`
    - :func:`clone_shallow`
    - :func:`shallow_clone_context`
    - :func:`get_clone_head_sha`
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

#: Strict public GitHub URL pattern. Rejects enterprise hosts, SSH URLs,
#: non-HTTPS schemes, and anything that is not exactly github.com.
GITHUB_URL_RE = re.compile(
    r"^https://github\.com/"
    r"(?P<owner>[A-Za-z0-9_.\-]+)/"
    r"(?P<repo>[A-Za-z0-9_.\-]+?)"  # non-greedy so trailing .git is stripped
    r"(?:\.git)?"
    r"(?:[/?#].*)?$"
)

GITHUB_API_BASE = "https://api.github.com"
GITHUB_REST_TIMEOUT_SECONDS = 10.0
CLONE_DEPTH = 50
CLONE_TIMEOUT_SECONDS = 120
MAX_REPO_SIZE_MB_DEFAULT = 250


@dataclass
class ParsedRepo:
    """Validated decomposition of a public GitHub URL."""

    owner: str
    repo: str
    canonical_url: str


@dataclass
class RepoMetadata:
    """Subset of GitHub REST repository metadata used by the pipeline."""

    owner: str
    repo: str
    default_branch: str = "main"
    description: str | None = None
    stars: int = 0
    forks: int = 0
    open_issues: int = 0
    is_private: bool = False
    is_archived: bool = False
    workflows: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


@dataclass
class CloneResult:
    """Outcome of a bounded shallow clone."""

    path: Path
    commit_sha: str | None
    size_mb: float


def parse_github_url(url: str) -> ParsedRepo:
    """Parse and validate a public GitHub repository URL.

    Args:
        url: Candidate URL, e.g. ``https://github.com/<owner>/<repo>``.

    Returns:
        Validated :class:`ParsedRepo` with a canonical ``.git``-free URL.

    Raises:
        ValueError: If the URL is not a public ``github.com`` HTTPS URL.
    """
    if not isinstance(url, str):
        raise ValueError("github_repo_url must be a string.")
    candidate = url.strip()
    match = GITHUB_URL_RE.match(candidate)
    if not match:
        raise ValueError(
            "Only public GitHub URLs are allowed: "
            "https://github.com/<owner>/<repo>."
        )
    owner = match.group("owner")
    repo = match.group("repo")
    if owner in {"", ".", ".."} or repo in {"", ".", ".."}:
        raise ValueError("Invalid GitHub owner/repo in URL.")
    return ParsedRepo(
        owner=owner, repo=repo, canonical_url=f"https://github.com/{owner}/{repo}"
    )


def is_public_repo_allowed(url: str) -> bool:
    """Return True only for well-formed public ``github.com`` HTTPS URLs.

    This is a syntactic gate (regex + host allow-list). Whether the repo is
    actually public is confirmed at fetch time via the GitHub REST API
    (``private == False``); private/enterprise hosts are rejected here.
    """
    try:
        parse_github_url(url)
    except ValueError:
        return False
    return True


def _github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "DevTrack-AI/0.3.0 (read-only inspector)",
    }
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_repo_metadata(url_or_owner: str, repo: str | None = None) -> RepoMetadata:
    """Fetch public repository metadata via the GitHub REST API.

    Args:
        url_or_owner: Full ``https://github.com/<owner>/<repo>`` URL, or the
            owner when ``repo`` is also given.
        repo: Optional repo name when the first argument is the owner.

    Raises:
        ValueError: If the URL is not an allowed public GitHub URL, or the
            repository is private.
        RuntimeError: On network/API failures (callers treat as non-fatal).
    """
    import httpx

    if repo is None:
        parsed = parse_github_url(url_or_owner)
    else:
        parsed = parse_github_url(f"https://github.com/{url_or_owner}/{repo}")

    try:
        with httpx.Client(timeout=GITHUB_REST_TIMEOUT_SECONDS) as client:
            resp = client.get(
                f"{GITHUB_API_BASE}/repos/{parsed.owner}/{parsed.repo}",
                headers=_github_headers(),
            )
            if resp.status_code == 404:
                raise ValueError(f"Repository not found or not public: {parsed.canonical_url}.")
            resp.raise_for_status()
            data = resp.json()
            workflows: list[str] = []
            try:
                wf_resp = client.get(
                    f"{GITHUB_API_BASE}/repos/{parsed.owner}/{parsed.repo}/contents/.github/workflows",
                    headers=_github_headers(),
                )
                if wf_resp.status_code == 200:
                    entries = wf_resp.json()
                    if isinstance(entries, list):
                        workflows = [
                            str(e.get("name", ""))
                            for e in entries
                            if isinstance(e, dict) and e.get("name")
                        ]
            except Exception:
                workflows = []  # workflow listing is best-effort only
    except ValueError:
        raise
    except Exception as exc:
        raise RuntimeError(f"GitHub REST request failed: {type(exc).__name__}") from exc

    if data.get("private") is True:
        raise ValueError("Only public GitHub repositories are permitted.")
    return RepoMetadata(
        owner=parsed.owner,
        repo=parsed.repo,
        default_branch=str(data.get("default_branch") or "main"),
        description=data.get("description"),
        stars=int(data.get("stargazers_count") or 0),
        forks=int(data.get("forks_count") or 0),
        open_issues=int(data.get("open_issues_count") or 0),
        is_private=bool(data.get("private", False)),
        is_archived=bool(data.get("archived", False)),
        workflows=workflows,
        raw={k: data.get(k) for k in ("full_name", "html_url", "language", "pushed_at")},
    )


def _dir_size_mb(path: Path) -> float:
    total = 0
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue
    return total / (1024 * 1024)


def clone_shallow(
    url: str,
    dest_dir: str | Path,
    *,
    depth: int = CLONE_DEPTH,
    timeout_seconds: int = CLONE_TIMEOUT_SECONDS,
    max_size_mb: float = MAX_REPO_SIZE_MB_DEFAULT,
) -> CloneResult:
    """Shallow-clone a public repo into a non-existing child dir (read-only).

    Uses ``git clone --depth 50`` with strict timeouts. Never executes any
    repository code — no hooks, no checkout scripts (files are present for
    static inspection only, nothing is run).

    ``git clone <url> <dest>`` requires ``dest`` to NOT exist (git creates
    it); the parent directory must exist. Callers must NOT pre-create
    ``dest`` with ``mkdir`` — create only the parent temp dir and let git
    create the ``checkout`` child.

    Args:
        url: Public GitHub URL (validated first).
        dest_dir: Non-existing path to clone into (parent must exist).
        depth: Clone depth (default 50).
        timeout_seconds: Subprocess timeout for the clone.
        max_size_mb: Reject checkouts larger than this.

    Raises:
        ValueError: On disallowed URL.
        RuntimeError: On clone failure, timeout, size-limit breach, or when
            ``dest`` already exists.
    """
    parsed = parse_github_url(url)  # validates allow-list first
    dest = Path(dest_dir)
    if dest.exists():
        raise RuntimeError(
            f"Clone destination must not pre-exist (git creates it): {dest}."
        )
    parent = dest.parent
    if str(parent) and not parent.is_dir():
        raise RuntimeError(f"Clone parent directory does not exist: {parent}.")
    try:
        completed = subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                str(depth),
                "--no-tags",
                parsed.canonical_url,
                str(dest),
            ],
            timeout=timeout_seconds,
            capture_output=True,
            text=True,
            shell=False,  # never use shell=True with untrusted input
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("git clone timed out.") from exc
    except FileNotFoundError as exc:
        raise RuntimeError("git binary not available.") from exc
    if completed.returncode != 0:
        stderr_tail = (completed.stderr or "")[-500:]
        raise RuntimeError(f"git clone failed: {stderr_tail}")
    size_mb = _dir_size_mb(dest)
    configured_cap = float(os.environ.get("MAX_REPO_SIZE_MB", str(max_size_mb)) or max_size_mb)
    if size_mb > configured_cap:
        raise RuntimeError(
            f"Cloned repository size {size_mb:.1f} MB exceeds cap {configured_cap:.0f} MB."
        )
    return CloneResult(path=dest, commit_sha=get_clone_head_sha(dest), size_mb=size_mb)


def get_clone_head_sha(clone_dir: str | Path) -> str | None:
    """Return the HEAD commit SHA of a clone (read-only git query)."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(clone_dir), "rev-parse", "HEAD"],
            timeout=15,
            capture_output=True,
            text=True,
            shell=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if completed.returncode != 0:
        return None
    sha = (completed.stdout or "").strip()
    return sha if re.fullmatch(r"[0-9a-f]{4,64}", sha) else None


@contextmanager
def shallow_clone_context(url: str) -> Iterator[CloneResult]:
    """Context manager: shallow-clone into an isolated temp dir, auto-cleaned.

    Yields:
        CloneResult pointing at the temporary checkout. The directory is
        removed on exit.

    Example:
        with shallow_clone_context(project.github_repo_url) as clone:
            run_all_scanners(clone.path)
    """
    # Validate before allocating any resources.
    parse_github_url(url)
    with tempfile.TemporaryDirectory(prefix="devtrack-clone-") as tmp:
        # git clone <url> <dest> requires dest to NOT exist — create only
        # the parent temp dir and let git create the checkout child.
        # Do NOT mkdir(dest) beforehand; TemporaryDirectory auto-cleans.
        dest = Path(tmp) / "checkout"
        yield clone_shallow(url, dest)
