"""The review surface reads evidence without token, model or mail access."""

import sqlite3
from unittest.mock import AsyncMock

import httpx
import pytest

from sellbird.review import build_review_app
from sellbird.review_data import Dataset, import_dataset, read_project
from sellbird.state import StateManager


def dataset():
    return Dataset.model_validate(
        {
            "project": "example",
            "product": "Example reporting",
            "offer": "Review one monthly report",
            "firms": [
                {
                    "id": "example-firm",
                    "name": "Example Accounting",
                    "source_url": "https://example.org/services",
                    "retrieved_on": "2026-11-11",
                    "published_on": None,
                    "evidence": "Public cloud bookkeeping service.",
                    "fit_reason": "Accountants preparing client reports could assess report automation.",
                    "sheets_evidence": "unknown",
                    "priority": "P1",
                    "buyer_role": "Accounting operations lead",
                    "validation_needed": "Confirm current tools and reporting need.",
                }
            ],
        }
    )


@pytest.mark.asyncio
async def test_import_is_idempotent_preserves_attempts_and_no_contacts(tmp_path):
    path = tmp_path / "research.db"
    state = StateManager(db_path=str(path))
    await state.init_db()
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE research_attempts(day TEXT)")
        db.execute("INSERT INTO research_attempts VALUES ('2026-11-11')")
    import_dataset(path, dataset())
    import_dataset(path, dataset())
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM companies").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM research_attempts").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM prospects").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM outbox").fetchone()[0] == 0
    assert read_project(path)["project"] == "example"


def test_duplicate_firms_and_unsafe_sources_rejected():
    data = dataset().model_dump(mode="json")
    data["firms"] *= 2
    with pytest.raises(ValueError):
        Dataset.model_validate(data)
    data = dataset().model_dump(mode="json")
    data["firms"][0]["source_url"] = "javascript:alert(1)"
    with pytest.raises(ValueError):
        Dataset.model_validate(data)


@pytest.mark.asyncio
async def test_review_is_readonly_escaped_and_no_native_dashboard(
    tmp_path, monkeypatch
):

    path = tmp_path / "research.db"
    await StateManager(db_path=str(path)).init_db()
    data = dataset()
    data.firms[0].name = "<script>alert(1)</script>"
    import_dataset(path, data)
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        before = list(db.iterdump())
    app = build_review_app(
        path,
        host="example.test",
        allowed_logins=["owner@example.org"],
        whois=AsyncMock(return_value="owner@example.org"),
    )
    headers = {
        "host": "example.test",
        "tailscale-user-login": "owner@example.org",
        "x-sellbird-client-ip": "100.64.0.9",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://example.test"
    ) as client:
        for route in ["/", "/healthz", "/api/project", "/api/companies"]:
            response = await client.get(route, headers=headers)
            assert response.status_code == 200
        html = (await client.get("/", headers=headers)).text
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html
        assert "Sending disabled" in html and "example" in html
        assert (await client.get("/api/settings", headers=headers)).status_code == 403
        assert (await client.post("/api/project", headers=headers)).status_code == 403
        assert (await client.get("/api/project")).status_code == 403
    with sqlite3.connect(path) as db:
        assert list(db.iterdump()) == before
    assert not any(route.path.startswith("/api/settings") for route in app.routes)


@pytest.mark.asyncio
async def test_conflict_rolls_back_project_update(tmp_path):
    path = tmp_path / "state.db"
    await StateManager(db_path=str(path)).init_db()
    original = dataset()
    import_dataset(path, original)
    changed = dataset()
    changed.offer = "Changed offer"
    changed.firms[0].name = "Different Example"
    with pytest.raises(ValueError):
        import_dataset(path, changed)
    assert read_project(path)["offer"] == original.offer
    other = dataset()
    other.project = "another"
    with pytest.raises(ValueError):
        import_dataset(path, other)
    assert read_project(path)["project"] == "example"
