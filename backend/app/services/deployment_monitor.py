"""SSRF-protected deployment health monitor (Track 3).

Every outbound check resolves the hostname via :func:`socket.getaddrinfo`
and rejects private, loopback, link-local, multicast, reserved, and
cloud-metadata addresses *before* any HTTP request is issued. Automatic
redirects are disabled; each redirect target is re-validated through the
same SSRF gate (max 3 hops).

Public API:
    - :func:`validate_target_url` (SSRF gate)
    - :func:`check_deployment_health`
    - :func:`discover_deployment_url`
    - :class:`DeploymentMonitor` (implements the Track 1 protocol ``check``)
"""

from __future__ import annotations

import ipaddress
import re
import socket
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

REQUEST_TIMEOUT_SECONDS = 10.0
MAX_REDIRECT_HOPS = 3

#: Explicitly blocked literals (cloud metadata + loopback), checked before DNS.
BLOCKED_HOSTNAMES = frozenset(
    {"localhost", "metadata.google.internal", "metadata.google.com"}
)
BLOCKED_IPS = frozenset({"169.254.169.254", "fd00:ec2::254"})

#: Regex for well-formed http(s) target URLs.
HTTP_URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)

URL_IN_TEXT_RE = re.compile(r"https?://[^\s)\"'<>`]+", re.IGNORECASE)

README_CANDIDATES = ("README.md", "readme.md", "README", "docs/README.md")
CONFIG_CANDIDATES = (
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yaml",
    "fly.toml",
    "render.yaml",
    "vercel.json",
    ".env.example",
)


class SSRFBlockedError(ValueError):
    """Raised when a deployment target fails the SSRF safety gate."""


def _ip_is_forbidden(ip: ipaddress._BaseAddress) -> bool:
    """True for any non-public-unicast address class."""
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or str(ip) in BLOCKED_IPS
    )


def resolve_and_validate(hostname: str) -> list[str]:
    """Resolve ``hostname`` and reject forbidden addresses.

    Args:
        hostname: DNS name or IP literal from the target URL.

    Returns:
        List of resolved IP strings (all verified public).

    Raises:
        SSRFBlockedError: If the hostname is blocked or resolves to a
            forbidden address.
    """
    host = (hostname or "").strip().rstrip(".").lower()
    if not host:
        raise SSRFBlockedError("Empty deployment hostname.")
    if host in BLOCKED_HOSTNAMES:
        raise SSRFBlockedError(f"Blocked deployment hostname: {host}.")
    # Fast path for IP literals (covers 127.0.0.1, 10/8, 192.168/16, ::1, …).
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and _ip_is_forbidden(literal):
        raise SSRFBlockedError(f"Blocked deployment IP literal: {host}.")
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SSRFBlockedError(f"Deployment hostname does not resolve: {host}.") from exc
    resolved: list[str] = []
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            raise SSRFBlockedError(f"Unparseable resolved address for {host}.")
        # Reject IPv4-mapped IPv6 loopback/private forms (::ffff:127.0.0.1).
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            if _ip_is_forbidden(ip.ipv4_mapped):
                raise SSRFBlockedError(f"Blocked mapped deployment IP for {host}.")
        if _ip_is_forbidden(ip):
            raise SSRFBlockedError(
                f"Deployment hostname {host} resolves to forbidden address."
            )
        resolved.append(ip_str)
    if not resolved:
        raise SSRFBlockedError(f"Deployment hostname {host} resolved to no addresses.")
    return resolved


def validate_target_url(url: str) -> str:
    """Apply the full SSRF gate; return the normalized URL or raise."""
    if not isinstance(url, str) or not HTTP_URL_RE.match(url.strip()):
        raise SSRFBlockedError("Deployment URL must be an http(s) URL.")
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise SSRFBlockedError("Deployment URL scheme must be http or https.")
    if not parsed.hostname:
        raise SSRFBlockedError("Deployment URL has no hostname.")
    if parsed.username or parsed.password:
        raise SSRFBlockedError("Deployment URL must not embed credentials.")
    resolve_and_validate(parsed.hostname)
    return url.strip()


@dataclass
class DeploymentHealth:
    """Result of one SSRF-guarded health check."""

    is_reachable: bool
    http_status_code: int | None
    https_valid: bool
    response_time_ms: float | None
    error_detail: str | None = None

    def to_dict(self) -> dict:
        return {
            "is_reachable": self.is_reachable,
            "http_status_code": self.http_status_code,
            "https_valid": self.https_valid,
            "response_time_ms": self.response_time_ms,
            "error_detail": self.error_detail,
        }


def check_deployment_health(
    target_url: str, *, timeout_seconds: float = REQUEST_TIMEOUT_SECONDS
) -> DeploymentHealth:
    """Perform an SSRF-protected HTTP health check.

    Redirects are followed manually (up to 3 hops) with every hop
    re-validated through :func:`validate_target_url`.
    """
    import httpx

    try:
        current = validate_target_url(target_url)
    except SSRFBlockedError as exc:
        return DeploymentHealth(
            is_reachable=False,
            http_status_code=None,
            https_valid=target_url.strip().lower().startswith("https://"),
            response_time_ms=None,
            error_detail=f"SSRF blocked: {exc}",
        )
    try:
        with httpx.Client(
            timeout=timeout_seconds, follow_redirects=False, max_redirects=0
        ) as client:
            started = time.perf_counter()
            hops = 0
            url = current
            while True:
                try:
                    response = client.get(url)
                except httpx.TimeoutException:
                    return DeploymentHealth(False, None, url.lower().startswith("https://"),
                                            (time.perf_counter() - started) * 1000, "request timed out")
                except httpx.ConnectError:
                    return DeploymentHealth(False, None, url.lower().startswith("https://"),
                                            (time.perf_counter() - started) * 1000, "connection refused/unreachable")
                except httpx.HTTPError as exc:
                    return DeploymentHealth(False, None, url.lower().startswith("https://"),
                                            (time.perf_counter() - started) * 1000,
                                            f"HTTP transport error: {type(exc).__name__}")
                status = response.status_code
                if status in (301, 302, 303, 307, 308):
                    hops += 1
                    if hops > MAX_REDIRECT_HOPS:
                        return DeploymentHealth(False, status, url.lower().startswith("https://"),
                                                (time.perf_counter() - started) * 1000,
                                                "too many redirects")
                    location = response.headers.get("location", "")
                    if not location:
                        return DeploymentHealth(False, status, url.lower().startswith("https://"),
                                                (time.perf_counter() - started) * 1000,
                                                "redirect without Location")
                    next_url = urljoin(url, location)
                    try:
                        next_url = validate_target_url(next_url)
                    except SSRFBlockedError as exc:
                        return DeploymentHealth(False, status, next_url.lower().startswith("https://") if isinstance(next_url, str) else False,
                                                (time.perf_counter() - started) * 1000,
                                                f"SSRF blocked redirect target: {exc}")
                    url = next_url
                    continue
                elapsed_ms = (time.perf_counter() - started) * 1000
                return DeploymentHealth(
                    is_reachable=200 <= status < 400,
                    http_status_code=status,
                    https_valid=url.lower().startswith("https://"),
                    response_time_ms=round(elapsed_ms, 2),
                    error_detail=None if 200 <= status < 400 else f"unexpected status {status}",
                )
    except Exception as exc:  # defensive: health checks never raise
        return DeploymentHealth(False, None, False, None, f"check failed: {type(exc).__name__}")


def _first_public_url(text: str) -> str | None:
    for match in URL_IN_TEXT_RE.finditer(text or ""):
        candidate = match.group(0).rstrip(".,;")
        try:
            parsed = urlparse(candidate)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                continue
            resolve_and_validate(parsed.hostname)
            return candidate
        except SSRFBlockedError:
            continue
    return None


def discover_deployment_url(
    repo_dir: str | Path, manual_override: str | None = None
) -> tuple[str | None, str]:
    """Discover a deployment URL from README/config, honoring manual override.

    Args:
        repo_dir: Root of the cloned repository checkout.
        manual_override: Explicit ``projects.deployment_url`` (SSRF-gated).

    Returns:
        ``(url_or_None, discovery_source)`` where source is one of
        ``"manual"`` | ``"readme"`` | ``"config"``. When nothing is found,
        returns ``(None, "manual")``.
    """
    if manual_override and manual_override.strip():
        try:
            return validate_target_url(manual_override.strip()), "manual"
        except SSRFBlockedError:
            return None, "manual"
    root = Path(repo_dir)
    for candidate in README_CANDIDATES:
        path = root / candidate
        if path.is_file():
            try:
                found = _first_public_url(path.read_text(encoding="utf-8", errors="replace")[:50000])
            except OSError:
                found = None
            if found:
                return found, "readme"
    for candidate in CONFIG_CANDIDATES:
        path = root / candidate
        if path.is_file():
            try:
                found = _first_public_url(path.read_text(encoding="utf-8", errors="replace")[:50000])
            except OSError:
                found = None
            if found:
                return found, "config"
    return None, "manual"


class DeploymentMonitor:
    """Concrete monitor satisfying Track 1's ``DeploymentMonitorProtocol``."""

    def check(self, target_url: str) -> dict:
        """Return {is_reachable, http_status_code, https_valid, response_time_ms, error_detail}."""
        return check_deployment_health(target_url).to_dict()
