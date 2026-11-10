# Manual research drafts

`sellbird-research` is a separate POSIX command for a small research-and-drafting trial. It never starts Sellbird's heartbeat, discovers companies, fetches evidence, opens a mailbox, verifies addresses, stages an Outbox message or sends email. The operator supplies source evidence and reviews every output. This command uses the existing signed-in Claude CLI with Sellbird's isolation flags; it does not fetch quota, extract/copy credentials, use Codex or fall back to an API provider.

Create a private directory and a mode-0600 JSON brief with `product`, `offer`, `target`, `language` (`English` or `Japanese`), and one to ten evidence objects (`id`, `claim`, `source_url`). Use only verified public claims and credential-free HTTPS source URLs without query strings. Do not put real brief content or outputs in this public repository. Keep inputs, database and drafts in private, unsynced storage.

```sh
sellbird-research --brief /private/operator-home/brief.json \
  --database /private/operator-home/research.db \
  --output /private/operator-home/new-draft.json
```

Both output and database parents must already be owned mode-0700 directories. The brief must be an owned regular file without group/world permissions, not a symlink, at most 32 KiB. Output creation is exclusive: an existing result is never overwritten. SQLite reserves an attempt before generation, across concurrent invocations; the limit is five attempts per JST calendar day, including failed attempts. There is at most one CLI model call, no retries, and a 120-second call timeout. This is a call-count cap, not a measured subscription-quota percentage.

The result always says `mode: draft-only` and `requires_review: true`. It preserves evidence and validates cited evidence IDs. Japanese and English drafts both have a 600-Unicode-character body ceiling; subjects have a 70-character ceiling. Drafts cannot contain HTTP links or email addresses. These checks do not prove factual correctness or make the draft suitable for sending. A human must check relevance, wording, source evidence, contact policy and the proposed next step. The command records usage through Brain and a metadata-only research event in the local SQLite activity log.

Provider override environment variables are rejected. Do not attach native Gmail credentials or SMTP credentials to this trial; use the organization's approved communication broker for any later, separately authorized outreach. No periodic job, browser binary or dashboard listener is installed by this command. Normal Sellbird commands retain their existing behavior and should not be used as a substitute for this restricted trial path.
