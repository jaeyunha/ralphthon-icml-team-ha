"""Exact-endpoint egress policy for broker-owned network requests."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Callable, Iterable
from urllib.parse import SplitResult, urlsplit, urlunsplit


class EgressDenied(PermissionError):
    """A network request does not satisfy the frozen broker policy."""


Resolver = Callable[[str, int], Iterable[str]]


def _canonical_url(value: str) -> SplitResult:
    parsed = urlsplit(value)
    if (
        not parsed.scheme
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise EgressDenied("invalid_endpoint_url")
    if parsed.scheme not in {"http", "https"}:
        raise EgressDenied("alternate_protocol_denied")
    if parsed.query:
        raise EgressDenied("query_not_permitted")
    try:
        _ = parsed.port
    except ValueError as exc:
        raise EgressDenied("invalid_port") from exc
    return parsed._replace(
        scheme=parsed.scheme.lower(), netloc=parsed.netloc.lower(), path=parsed.path or "/"
    )


def _public_address(value: str) -> str:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise EgressDenied("dns_returned_non_ip_address") from exc
    if not address.is_global:
        raise EgressDenied("private_or_metadata_target_denied")
    return str(address)


def system_resolver(host: str, port: int) -> tuple[str, ...]:
    return tuple(
        sorted({item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)})
    )


@dataclass(frozen=True)
class EndpointPolicy:
    """One frozen URL, with DNS pinning checked immediately before connection."""

    endpoint: str
    resolver: Resolver = system_resolver
    require_tls: bool = True

    def __post_init__(self) -> None:
        parsed = _canonical_url(self.endpoint)
        if self.require_tls and parsed.scheme != "https":
            raise ValueError("TLS is required for broker endpoints")
        object.__setattr__(self, "endpoint", urlunsplit(parsed))

    @property
    def parsed(self) -> SplitResult:
        return _canonical_url(self.endpoint)

    @property
    def port(self) -> int:
        return self.parsed.port or (443 if self.parsed.scheme == "https" else 80)

    def authorize(
        self, url: str, *, method: str = "GET", redirects: bool = False, websocket: bool = False
    ) -> tuple[str, ...]:
        """Return a pinned public address set or reject before an HTTP client runs."""
        requested = _canonical_url(url)
        expected = self.parsed
        if method != "GET":
            raise EgressDenied("method_denied")
        if redirects:
            raise EgressDenied("redirects_denied")
        if websocket:
            raise EgressDenied("websocket_denied")
        if requested.scheme != expected.scheme:
            raise EgressDenied("alternate_protocol_denied")
        if requested.hostname != expected.hostname:
            raise EgressDenied("host_denied")
        if (requested.port or (443 if requested.scheme == "https" else 80)) != self.port:
            raise EgressDenied("port_denied")
        if requested.path != expected.path:
            raise EgressDenied("path_denied")
        first = tuple(
            sorted({_public_address(ip) for ip in self.resolver(expected.hostname, self.port)})
        )
        second = tuple(
            sorted({_public_address(ip) for ip in self.resolver(expected.hostname, self.port)})
        )
        if not first or first != second:
            raise EgressDenied("dns_rebinding_denied")
        return first

    def verify_tls(self, *, peer_hostname: str, tls_version: str | None) -> None:
        """Validate values reported by the caller's TLS stack before request use."""
        if not self.require_tls:
            return
        if peer_hostname.lower().rstrip(".") != self.parsed.hostname.lower().rstrip("."):
            raise EgressDenied("tls_hostname_denied")
        if tls_version is None or tls_version < "TLSv1.2":
            raise EgressDenied("tls_version_denied")

    def connection_options(self, url: str) -> dict[str, object]:
        """A client-facing request contract; callers must not override these values."""
        addresses = self.authorize(url)
        return {
            "url": self.endpoint,
            "method": "GET",
            "allow_redirects": False,
            "proxy": None,
            "connect_hostnames": addresses,
            "server_hostname": self.parsed.hostname,
            "require_tls": self.require_tls,
        }
