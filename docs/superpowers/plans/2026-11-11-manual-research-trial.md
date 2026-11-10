# Manual Research Trial Implementation Plan

> Execute inline, one tested unit at a time. This plan uses no delegated agents.

**Goal:** Add a manually invoked, evidence-grounded drafting command with no mailbox or send path.

**Architecture:** A separate `sellbird.research` command uses the existing isolated Claude runtime through Brain.think with retries disabled. It reads an operator-supplied brief, reserves a bounded daily attempt in SQLite before generation, writes a private review-only result and records an activity event. It never invokes the heartbeat, sender, trainer, quota API or mailbox provider.

**Tech Stack:** Python 3.12, existing Pydantic/SQLite/pytest and Sellbird Brain.

## Constraints

- Public repository: fictional fixtures only; real product configuration and lead evidence stay in a private runtime home, never in a commit or PR.
- Signed-in Claude subscription CLI only; reject API/provider override environment variables; no credential extraction/copying or quota API.
- One CLI call per invocation, 120-second timeout, no retries; five attempts per Asia/Tokyo calendar day, reserved transactionally before the call.
- No sends, recipient-address input, mailbox credentials, browser install, service scheduler or public listener.
- Input at most 32 KiB, regular owner-held 0600 file; output must be new, 0600, under a private owned directory.
- Require source evidence; preserve source IDs in the review result; no URL or email address in generated body; enforce character limits for Japanese text.

## Task 1: Independent research command

Files: `sellbird/research.py`, `tests/test_research.py`, `pyproject.toml`, `docs/manual-research.md`.

- [x] Run upstream baseline and record its result.
- [x] Write failing tests for unsafe input/output, absent evidence, Japanese character limits, one-call/no-retry behavior, API override rejection, attempt cap, and no quota/mail path.
- [x] Implement `Brief`, `Draft`, `reserve_attempt(database, day)`, `generate(brief, state, brain)` and the independent `sellbird-research` entry point.
- [ ] Run focused and full tests. Use offline Claude CLI isolation test against the installed CLI separately.
- [ ] Commit with DCO sign-off and publish a fork-local PR; preserve upstream main.

## Task 2: m1 trial

- [ ] Install a pinned upstream/fork worktree and an isolated venv on m1, preserving the cluster's other CLI versions and services.
- [ ] Create `~/srv/sellbird/private` mode 0700, with disabled email and LinkedIn, approval required, JST quiet hours, modest subscription budget and privately held product/qualification rules.
- [ ] Run the command using the existing signed-in CLI, verify output and SQLite audit, and independently confirm that no sender/outbox or quota code ran.
- [ ] Publish only a sanitized installation receipt to files.lab; keep business-specific configuration and drafts private. Record durable inventory in the correct KMS tier.
- [ ] Document manual operation and rollback. No loop/autostart is installed for this trial.
