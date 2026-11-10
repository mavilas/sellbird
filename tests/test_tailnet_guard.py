"""No token is created; proxy and original tailnet identity are both required."""

from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from sellbird.tailnet_guard import TailnetGuard

HEADERS = {
    "host": "example.test",
    "tailscale-user-login": "owner@example.org",
    "x-sellbird-client-ip": "100.64.0.9",
}


def app(resolver=None):
    inner = FastAPI()

    @inner.get("/api/project")
    def project():
        return {"project": "example"}

    return TailnetGuard(
        inner,
        host="example.test",
        allowed_logins={"owner@example.org"},
        whois=resolver or AsyncMock(return_value="owner@example.org"),
    )


@pytest.mark.asyncio
async def test_allowed_proxy_and_original_user():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="https://example.test"
    ) as client:
        assert (await client.get("/api/project", headers=HEADERS)).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("remove", ["tailscale-user-login", "x-sellbird-client-ip"])
async def test_anonymous_or_identity_only_spoof_denied(remove):
    headers = dict(HEADERS)
    headers.pop(remove)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="https://example.test"
    ) as client:
        assert (await client.get("/api/project", headers=headers)).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"host": "evil.example"},
        {"tailscale-user-login": "other@example.org"},
        {"origin": "https://evil.example"},
        {"sec-fetch-site": "cross-site"},
        {"upgrade": "websocket"},
        {"connection": "upgrade"},
        {"x-sellbird-client-ip": "127.0.0.1"},
    ],
)
async def test_bad_provenance_and_upgrade_denied(changes):
    headers = {**HEADERS, **changes}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="https://example.test"
    ) as client:
        assert (await client.get("/api/project", headers=headers)).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("identity", [None, "other@example.org"])
async def test_unallowed_original_ip_identity_denied(identity):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app(AsyncMock(return_value=identity))),
        base_url="https://example.test",
    ) as client:
        assert (await client.get("/api/project", headers=HEADERS)).status_code == 403


@pytest.mark.asyncio
async def test_resolver_failure_denies_without_error_details():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=app(AsyncMock(side_effect=RuntimeError("private-details")))
        ),
        base_url="https://example.test",
    ) as client:
        response = await client.get("/api/project", headers=HEADERS)
        assert response.status_code == 403 and "private-details" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE"]
)
async def test_every_nonread_method_denied(method):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="https://example.test"
    ) as client:
        assert (
            await client.request(method, "/api/project", headers=HEADERS)
        ).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/settings",
        "/api/sellbird/start",
        "/api/instance",
        "/api/usage",
        "/api/today/../settings",
        "/api/%73ettings",
        "/static/../data/dashboard-token",
    ],
)
async def test_unapproved_paths_denied(path):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="https://example.test"
    ) as client:
        assert (await client.get(path, headers=HEADERS)).status_code == 403


@pytest.mark.asyncio
async def test_duplicate_identity_headers_and_nonloopback_peer_denied():
    for headers, peer in [
        (
            list(HEADERS.items()) + [("tailscale-user-login", "other@example.org")],
            ("127.0.0.1", 123),
        ),
        (HEADERS, ("100.64.0.2", 123)),
    ]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app(), client=peer),
            base_url="https://example.test",
        ) as client:
            assert (
                await client.get("/api/project", headers=headers)
            ).status_code == 403


@pytest.mark.asyncio
async def test_whois_cache_and_tagged_identity(monkeypatch):
    import json

    from sellbird.tailnet_guard import TailnetWhois

    process = AsyncMock()
    process.returncode = 0
    process.communicate.return_value = (
        json.dumps(
            {"Node": {}, "UserProfile": {"LoginName": "owner@example.org"}}
        ).encode(),
        b"",
    )
    spawn = AsyncMock(return_value=process)
    monkeypatch.setattr("asyncio.create_subprocess_exec", spawn)
    resolver = TailnetWhois("/example/tailscale")
    assert await resolver("100.64.0.9") == "owner@example.org"
    assert await resolver("100.64.0.9") == "owner@example.org"
    spawn.assert_awaited_once()
    process.communicate.return_value = (
        json.dumps(
            {
                "Node": {"Tags": ["tag:server"]},
                "UserProfile": {"LoginName": "owner@example.org"},
            }
        ).encode(),
        b"",
    )
    assert await resolver("100.64.0.10") is None
    assert await resolver("127.0.0.1") is None


@pytest.mark.asyncio
async def test_whois_timeout_terminates_and_reaps(monkeypatch):
    import asyncio

    from sellbird.tailnet_guard import TailnetWhois

    process = AsyncMock()
    process.returncode = None
    process.terminate = __import__("unittest.mock", fromlist=["Mock"]).Mock()
    process.communicate.side_effect = asyncio.TimeoutError
    monkeypatch.setattr(
        "asyncio.create_subprocess_exec", AsyncMock(return_value=process)
    )
    with pytest.raises(asyncio.TimeoutError):
        await TailnetWhois()("100.64.0.9")
    process.terminate.assert_called_once()
    process.wait.assert_awaited_once()
