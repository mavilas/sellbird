# sellbird finno project and private ingress plan

> Execute inline. No delegation or automatic outreach.

**Goal:** Serve the reviewed Sellbird interface at sb.lab.leomares.com with a private, lowercase finno project and thirty evidence-qualified firms.

**Architecture:** Keep the application on m1 loopback and use the existing Tailscale daemon for HTTPS transit from m2 Caddy. Use an isolated read-only ASGI app on the native Sellbird database; do not load native dashboard, token, quota, credential or control routes. Verify both the proxy's Serve identity and the original browser IP's Tailscale WhoIs identity; require the private allowed-operator list. Publish only explicit read routes; block all mutation, quota, credential and process-control routes.

**Constraints:** No plaintext persisted token, public listener, Funnel, heartbeat, autopilot, inbox access or sending. All real dataset/configuration stays private on m1, outside the public fork. Caddy and Serve changes require exact packet GO. Preserve unrelated routes and Serve entries. Project name is finno, case-sensitive. No claim of Google Sheets usage without explicit evidence.

1. Read the existing finno research workbook through OpenClaw after owner/ACL verification. Retain only firm-level public fields. Recheck official profiles and add independent firms until exactly thirty unique qualified firms pass evidence checks. Mark missing Sheets evidence and contact policy explicitly; do not submit forms.
2. Add an isolated, tested read-only dashboard adapter and auth guard, with negative tests for missing/forged identity, wrong operator, cross-origin requests, mutation paths, unsafe headers, provider failure, and accidental token/quota access. Use a narrow evidence review interface and preserve the existing manual drafting command.
3. Add a homelab deployment specification, loopback LaunchAgent and exact sb.lab route candidate. Include memory/disk budget, readbacks, log rotation, monitor and rollback. Review source/CI before merge, and review live packet before any listener/Serve/Caddy effect.
4. Configure lowercase finno, import reviewed firm records transactionally with a backup and idempotent checks. Verify exact count, deduplication, source dates and disabled communication state.
5. After GO, install pinned source, start one loopback service, add only the new private Serve mapping and route, and verify authenticated HTML/data plus anonymous denial using a real browser. Publish sanitized evidence and a final inventory update; keep the firms private in the app.
