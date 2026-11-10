"""Manual research never acquires a mailbox or contacts a prospect."""
import json
from unittest.mock import AsyncMock

import pytest

from sellbird.research import Brief, Draft, generate, reserve_attempt, subscription_environment


def brief():
    return Brief.model_validate({
        "product": "Example reporting tool", "offer": "Set up one monthly report",
        "target": "Example Accounting", "language": "Japanese",
        "evidence": [{"id": "e1", "claim": "Offers monthly reports",
                      "source_url": "https://example.org/services"}],
    })


def test_requires_evidence():
    payload=brief().model_dump();payload["evidence"]=[]
    with pytest.raises(ValueError): Brief.model_validate(payload)


def test_japanese_length_uses_characters():
    with pytest.raises(ValueError):
        Draft.model_validate({"subject":"ご相談", "body":"あ"*601, "evidence_ids":["e1"]})


@pytest.mark.parametrize("body", ["Visit https://example.org", "Email hello@example.org"])
def test_draft_does_not_create_contact_or_link_routes(body):
    with pytest.raises(ValueError): Draft.model_validate({"subject":"Question", "body":body,"evidence_ids":["e1"]})


def test_subscription_override_refused_without_printing_value():
    with pytest.raises(ValueError) as error: subscription_environment({"ANTHROPIC_API_KEY":"fictional-value"})
    assert "fictional-value" not in str(error.value)
    subscription_environment({"PATH":"/usr/bin"})


def test_attempts_reserved_before_calls_and_capped(tmp_path):
    database=tmp_path/"state.db"
    for _ in range(5):reserve_attempt(database,"2026-11-11")
    with pytest.raises(ValueError):reserve_attempt(database,"2026-11-11")
    reserve_attempt(database,"2026-11-12")


@pytest.mark.asyncio
async def test_exactly_one_call_no_retry_no_mail_or_quota(monkeypatch):
    from sellbird.integrations import quota
    monkeypatch.setattr(quota,"get_oauth_token",lambda:pytest.fail("must not read credentials"))
    brain=AsyncMock();brain.think.return_value=json.dumps({"subject":"ご相談", "body":"月次報告についてお伺いできますか。", "evidence_ids":["e1"]})
    state=AsyncMock()
    result=await generate(brief(),state,brain)
    assert result["requires_review"] is True
    assert result["mode"]=="draft-only"
    brain.think.assert_awaited_once()
    assert brain.think.call_args.kwargs["max_retries"]==0
    assert brain.think.call_args.kwargs["timeout"]==120
    state.log_action.assert_awaited_once()


@pytest.mark.asyncio
async def test_unknown_evidence_reference_is_rejected():
    brain=AsyncMock();brain.think.return_value=json.dumps({"subject":"Question", "body":"A question", "evidence_ids":["invented"]})
    with pytest.raises(ValueError):await generate(brief(),AsyncMock(),brain)


def test_concurrent_reservations_share_one_cap(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    def attempt(_):
        try:reserve_attempt(tmp_path/"state.db","2026-11-11");return True
        except ValueError:return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(attempt,range(8)))==5


@pytest.mark.skipif(__import__('os').name!='posix',reason='POSIX private file contract')
def test_private_brief_rejects_symlinks_permissions_and_oversize(tmp_path):
    import os
    from sellbird.research import read_brief
    file=tmp_path/"brief.json";file.write_text(brief().model_dump_json());file.chmod(0o600)
    assert read_brief(file).target==brief().target
    link=tmp_path/"link.json";link.symlink_to(file)
    with pytest.raises(OSError):read_brief(link)
    file.chmod(0o644)
    with pytest.raises(ValueError):read_brief(file)
    file.chmod(0o600);file.write_text(' '*32769)
    with pytest.raises(ValueError):read_brief(file)


@pytest.mark.asyncio
@pytest.mark.skipif(__import__('os').name!='posix',reason='POSIX private file contract')
async def test_failure_consumes_attempt_and_removes_partial_output(tmp_path,monkeypatch):
    import argparse
    import sqlite3
    import sellbird.brain
    from sellbird.research import run
    tmp_path.chmod(0o700)
    file=tmp_path/"brief.json";file.write_text(brief().model_dump_json());file.chmod(0o600)
    fake=AsyncMock();fake.think.return_value='invalid-json'
    monkeypatch.setattr(sellbird.brain,"Brain",lambda *args:fake)
    args=argparse.Namespace(brief=file,output=tmp_path/"draft.json",database=tmp_path/"state.db")
    awaitable=run(args)
    with pytest.raises(ValueError):await awaitable
    assert not args.output.exists()
    with sqlite3.connect(args.database) as db:
        assert db.execute('SELECT count(*) FROM research_attempts').fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM outbox').fetchone()[0]==0
    args.output.write_text('existing');args.output.chmod(0o600)
    with pytest.raises(FileExistsError):await run(args)
    assert args.output.read_text()=='existing'
    fake.think.assert_awaited_once()
