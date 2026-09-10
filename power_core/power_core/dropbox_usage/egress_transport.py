"""Resilient egress transport plus self-diagnostics for Dropbox API calls.

Dropbox DNS rotates edge IPs and some are unreachable from us-central1;
a single dead address must not sink the whole request. The adapter below
tries every resolved address with a short per-attempt timeout instead of
relying on one slow system default. Diagnose_egress records resolved
addresses, per-IP reachability, and routing state whenever a Dropbox
connection fails, so the next incident carries its own root cause.
"""
import http.client
import logging
import socket
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3 import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.poolmanager import PoolManager

logger = logging.getLogger(__name__)

PER_IP_TIMEOUT = 8


def connect_resilient(host, port, timeout=PER_IP_TIMEOUT):
    """Connect trying every resolved address with a short per-attempt timeout."""
    errors = []
    for _, _, _, _, sockaddr in socket.getaddrinfo(host, port):
        start = time.time()
        try:
            sock = socket.create_connection((sockaddr[0], port), timeout=timeout)
            return sock
        except Exception as exc:  # noqa: BLE001 (collect per-address failures)
            errors.append(f"{sockaddr[0]}: {exc!r} in {time.time() - start:.2f}s")
    raise OSError(f"all {len(errors)} addresses failed for {host}: {errors}")


class _ResilientHTTPConnection(http.client.HTTPConnection):
    """Plain HTTP connection walking all resolved addresses."""

    def connect(self):
        """Connect to the first reachable resolved address."""
        self.sock = connect_resilient(self.host, self.port)


class _ResilientHTTPSConnection(http.client.HTTPSConnection):
    """TLS connection walking all resolved addresses, then wrapped like stdlib."""

    def connect(self):
        """Connect to the first reachable address and wrap with TLS."""
        sock = connect_resilient(self.host, self.port)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _ResilientHTTPConnectionPool(HTTPConnectionPool):
    """HTTP pool using resilient connections."""

    ConnectionCls = _ResilientHTTPConnection


class _ResilientHTTPSConnectionPool(HTTPSConnectionPool):
    """HTTPS pool using resilient connections."""

    ConnectionCls = _ResilientHTTPSConnection


class _ResilientPoolManager(PoolManager):
    """Pool manager serving resilient pools for both schemes."""

    pool_classes_by_scheme = {
        "http": _ResilientHTTPConnectionPool,
        "https": _ResilientHTTPSConnectionPool,
    }


class ResilientAdapter(HTTPAdapter):
    """Requests adapter routing everything through resilient pools."""

    def init_poolmanager(self, *args, **kwargs):
        """Build the pool manager with resilient connection classes."""
        self.poolmanager = _ResilientPoolManager(*args, **kwargs)


def resilient_session():
    """Build a requests session with resilient egress transport."""
    session = requests.Session()
    session.mount("https://", ResilientAdapter())
    session.mount("http://", ResilientAdapter())
    return session


def parse_proc_net_route(text):
    """Extract destination hex values from /proc/net/route contents."""
    destinations = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            destinations.append(parts[1])
    return destinations


def diagnose_egress(host, port=443):
    """Log resolved addresses, per-IP TCP reachability, and routing state."""
    try:
        infos = socket.getaddrinfo(host, port)
    except Exception as exc:  # noqa: BLE001 (diagnostic context)
        logger.error(f"EGRESS-DIAG {host}: DNS failed: {exc!r}")
        return
    for _, _, _, _, sockaddr in infos:
        label = "IPv6" if ":" in sockaddr[0] else "IPv4"
        start = time.time()
        try:
            sock = socket.create_connection((sockaddr[0], port), timeout=5)
            sock.close()
            logger.error(
                f"EGRESS-DIAG {host}: TCP {label} {sockaddr[0]} "
                f"OK in {time.time() - start:.2f}s"
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                f"EGRESS-DIAG {host}: TCP {label} {sockaddr[0]} "
                f"FAIL in {time.time() - start:.2f}s: {exc!r}"
            )
    try:
        with open("/proc/net/route") as handle:
            destinations = parse_proc_net_route(handle.read())
        logger.error(
            f"EGRESS-DIAG {host}: routes={destinations} "
            f"default={'00000000' in destinations}"
        )
    except OSError as exc:
        logger.error(f"EGRESS-DIAG {host}: no route table: {exc!r}")
    try:
        with open("/proc/net/if_inet6") as handle:
            logger.error(
                f"EGRESS-DIAG {host}: if_inet6_lines={len(handle.readlines())}"
            )
    except OSError as exc:
        logger.error(f"EGRESS-DIAG {host}: no IPv6 stack: {exc!r}")
