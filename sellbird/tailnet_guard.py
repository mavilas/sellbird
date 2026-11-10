"""Read-only Serve guard. Local services sharing this OS account are trusted.

Serve strips and replaces its identity header. Caddy must independently replace
X-Sellbird-Client-IP with the connection's remote IP. Check both identities: the
Serve identity alone belongs to the proxy, not the browser behind Caddy.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import time

SECURITY_HEADERS = [
    (b"cache-control", b"no-store"),
    (b"referrer-policy", b"no-referrer"),
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (
        b"content-security-policy",
        b"default-src 'none'; style-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
    ),
]

READ_PATHS = frozenset({"/", "/healthz", "/api/project", "/api/companies"})
STATIC_PATHS = frozenset({"/static/review.css"})


def tailnet_ip(value):
    try:
        address = ipaddress.ip_address(value)
        return address in ipaddress.ip_network(
            "100.64.0.0/10"
        ) or address in ipaddress.ip_network("fd7a:115c:a1e0::/48")
    except ValueError:
        return False


class TailnetWhois:
    """Bounded local daemon lookups; positive-only 30s cache, no credential access."""

    def __init__(self, executable="/opt/homebrew/bin/tailscale"):
        self.executable = executable
        self.cache = {}
        self.slots = asyncio.Semaphore(4)

    async def __call__(self, address):
        if not tailnet_ip(address):
            return None
        cached = self.cache.get(address)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        if self.slots.locked():
            return None
        async with self.slots:
            process = await asyncio.create_subprocess_exec(
                self.executable,
                "whois",
                "--json",
                address,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                output, _ = await asyncio.wait_for(process.communicate(), 2)
            except BaseException:
                if process.returncode is None:
                    process.kill()
                await process.wait()
                raise
        if process.returncode or len(output) > 65536:
            return None
        payload = json.loads(output)
        if payload.get("Node", {}).get("Tags"):
            return None
        login = payload.get("UserProfile", {}).get("LoginName")
        if not isinstance(login, str) or not login:
            return None
        if len(self.cache) >= 64:
            self.cache.pop(next(iter(self.cache)))
        self.cache[address] = (time.monotonic() + 30, login.lower())
        return login.lower()


class TailnetGuard:
    def __init__(self, app, *, host, allowed_logins, whois):
        self.app = app
        self.host = host
        self.allowed_logins = frozenset(login.lower() for login in allowed_logins)
        self.whois = whois

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            return await self.app(scope, receive, send)
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope["type"] != "http":
            return

        async def deny():
            await send(
                {
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [
                        (b"content-type", b"application/json"),
                        *SECURITY_HEADERS,
                    ],
                }
            )
            await send(
                {"type": "http.response.body", "body": b'{"error":"request_denied"}'}
            )

        headers = {}
        for key, value in scope.get("headers", []):
            headers.setdefault(key.lower(), []).append(value.decode("latin1"))
        critical = (
            b"host",
            b"origin",
            b"tailscale-user-login",
            b"x-sellbird-client-ip",
        )
        if any(len(headers.get(key, [])) > 1 for key in critical):
            return await deny()

        def one(key):
            return next(iter(headers.get(key, [])), "")

        path = scope.get("path", "")
        raw = scope.get("raw_path", path.encode())
        peer = (scope.get("client") or ("", 0))[0]
        if peer not in ("127.0.0.1", "::1") or one(b"host") != self.host:
            return await deny()
        if scope.get("method") not in ("GET", "HEAD"):
            return await deny()
        if b"%" in raw or b"\\" in raw or ".." in path.split("/"):
            return await deny()
        if path not in READ_PATHS and path not in STATIC_PATHS:
            return await deny()
        if b"upgrade" in headers or "upgrade" in one(b"connection").lower():
            return await deny()
        if one(b"origin") and one(b"origin") != "https://" + self.host:
            return await deny()
        if one(b"sec-fetch-site") not in ("", "none", "same-origin"):
            return await deny()
        if one(b"tailscale-user-login").lower() not in self.allowed_logins:
            return await deny()
        address = one(b"x-sellbird-client-ip")
        if not tailnet_ip(address):
            return await deny()
        try:
            login = await self.whois(address)
        except Exception:  # noqa: BLE001 - identity lookup must fail closed
            return await deny()
        if login not in self.allowed_logins:
            return await deny()
        scope.setdefault("state", {})["principal"] = "user"

        async def secured(message):
            if message["type"] == "http.response.start":
                names = {key for key, _ in SECURITY_HEADERS}
                message = {
                    **message,
                    "headers": [
                        (k, v)
                        for k, v in message.get("headers", [])
                        if k.lower() not in names
                    ]
                    + SECURITY_HEADERS,
                }
            await send(message)

        await self.app(scope, receive, secured)
