"""Peer URL checks and bounded HTTP reads.

Link-local and metadata addresses are rejected before any socket is opened.
Loopback and private addresses stay allowed so two local nodes can sync.
"""

from __future__ import annotations

import ipaddress
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import Any

from chain.errors import ChainError

_MAX_URL_LENGTH = 200
_MAX_RESPONSE_BYTES = 2_000_000
_TIMEOUT_SECONDS = 3
_HOST_RE = re.compile(r"(?=.{1,253}$)[A-Za-z0-9.-]+$")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        raise ChainError("redirects are not allowed")


def normalize_origin(url: str) -> str:
    """Return scheme://host:port or raise ChainError. Does not fetch."""
    if not isinstance(url, str) or not url.strip() or len(url) > _MAX_URL_LENGTH:
        raise ChainError("invalid peer url")
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ChainError("peer url must be http or https")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ChainError("invalid peer url")
    if parsed.path not in {"", "/"}:
        raise ChainError("peer url must not include a path")
    host = parsed.hostname
    port = parsed.port
    if host is None or port is None:
        raise ChainError("peer url needs a host and port")
    if not 1 <= port <= 65535:
        raise ChainError("invalid peer port")
    canonical_host = _canonical_host(host)
    for ip in _resolve(canonical_host):
        if _blocked(ip):
            raise ChainError("peer address is not allowed")
    display = f"[{canonical_host}]" if ":" in canonical_host else canonical_host
    return f"{parsed.scheme}://{display}:{port}"


def request_json(
    method: str,
    url: str,
    payload: Mapping[str, Any] | None = None,
    *,
    token: str = "",
    timeout: float = _TIMEOUT_SECONDS,
    max_bytes: int = _MAX_RESPONSE_BYTES,
) -> tuple[int, dict]:
    headers = {
        "Accept": "application/json",
        "X-Chain-Request": "1",
        "User-Agent": "blockchain-first",
    }
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            body = _read_limited(response, max_bytes)
            status = response.status
    except urllib.error.HTTPError as err:
        body = err.read(min(max_bytes, 16_384))
        status = err.code
    parsed = _decode_object(body)
    return status, parsed


def fetch_chain(origin: str) -> list | None:
    """GET {origin}/chain. Returns None when the peer is unreachable or unreadable."""
    try:
        origin = normalize_origin(origin)
        status, payload = request_json("GET", origin + "/chain", timeout=_TIMEOUT_SECONDS)
    except (urllib.error.URLError, TimeoutError, OSError, ChainError, ValueError):
        return None
    if status != 200:
        return None
    chain = payload.get("chain")
    length = payload.get("length")
    if not isinstance(chain, list) or length != len(chain):
        return None
    return chain


def _canonical_host(host: str) -> str:
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        if not _HOST_RE.fullmatch(host) or ".." in host or host.startswith("-"):
            raise ChainError("invalid peer host") from None
        if not re.search(r"[A-Za-z]", host):
            raise ChainError("invalid peer host") from None
        return host.lower().rstrip(".")


def _resolve(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as err:
        raise ChainError("peer host did not resolve") from err
    addresses = []
    for info in infos:
        addresses.append(ipaddress.ip_address(info[4][0]))
    if not addresses:
        raise ChainError("peer host did not resolve")
    return addresses


def _blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    # Python treats 169.254.0.0/16 as private and some multicast addresses as
    # global, so those flags are not enough on their own. Link-local is how
    # cloud metadata services are reached.
    if ip.is_multicast or ip.is_link_local or ip.is_unspecified:
        return True
    if ip.is_loopback or ip.is_private or ip.is_global:
        return False
    return True


def _read_limited(response, max_bytes: int) -> bytes:
    body = response.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise ChainError("peer response is too large")
    content_type = response.headers.get("Content-Type", "")
    if not content_type.startswith("application/json"):
        raise ChainError("peer response is not JSON")
    return body


def _decode_object(body: bytes) -> dict:
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise ChainError("response is not JSON") from err
    if not isinstance(parsed, dict):
        raise ChainError("response is not a JSON object")
    return parsed
