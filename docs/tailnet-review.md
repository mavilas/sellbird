# Private evidence review

Run `python -m sellbird.review --settings /private/path/review.json` to serve a
single imported research project. The settings file must be owner-only JSON with
`database`, `host`, `allowed_logins`, and `port`. The process binds IPv4 loopback
only, with one worker, no access log, and a 32-connection concurrency limit.
Deploy a private HTTPS reverse proxy separately. This mode provides project,
company-evidence and health reads; it has no write, contact, model, credential,
outbox or heartbeat routes. The native dashboard remains unchanged.

Import a validated `review_data.Dataset` using `import_dataset` after native
`StateManager.init_db()` and an owner-only SQLite backup. Imports are atomic,
idempotent, and refuse identifier conflicts and cross-project reuse. They preserve
native attempt counters and never create prospects or outbox items. Project IDs
are lowercase. Store real configuration and firm data outside this public repo.
Use one database per project. `research-qualified` describes public evidence fit;
it does not establish buying intent, current internal tools, or pilot readiness.

The trust boundary is the machine running the service plus the HTTPS proxy.
Tailscale Serve must strip incoming identity headers and supply its own identity.
The proxy must overwrite `X-Sellbird-Client-IP` with its actual connection peer,
ignoring incoming versions and forwarded-for claims. The guard requires both the
Serve proxy identity and a daemon WhoIs lookup of that original tailnet client
IP to match the private operator allowlist. Tagged devices and lookup failures
are denied. Authenticated operators get read access to the entire project.
Local processes running on the service host are trusted: a local process that
forges BOTH a valid operator header and a valid allowed tailnet IP can pass.
A forged identity header alone is denied. This does not isolate an app from a
compromised host or another process with the same OS account.

All HTTP routes require identity, including health and CSS. Only explicit GET
and HEAD paths are admitted; writes, WebSockets, cross-origin browser requests,
path tricks, duplicate critical headers and unexpected hosts are denied. The app
uses SQLite read-only connections with query-only enabled. WhoIs uses the local
daemon with four concurrent processes at most, a two-second timeout and a
30-second positive-only cache (at most 64 entries). A timeout sends TERM and
waits one more second; a surviving helper disables further lookups and emits
a metadata-only error for operator intervention. No SIGKILL is used. Serve and the public-facing
proxy must have their own connection bounds. No application token is created.

Rollback: stop the single review LaunchAgent, remove only its Serve mapping,
and remove only its proxy virtual host using a saved configuration and graceful
load. Restore the private SQLite backup only if reverting the import is desired;
that backup includes the manual-draft attempt counter, so do not restore stale
state merely to redeploy source. Existing native CLI drafting remains manual.
