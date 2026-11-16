"""Isolated Sellbird evidence review. No native control routes or credentials."""

from __future__ import annotations

import argparse
from html import escape
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from starlette.middleware import Middleware

from sellbird.review_data import read_private_json, read_project
from sellbird.tailnet_guard import TailnetGuard, TailnetWhois


def render(project):
    cards = []
    for firm in project["firms"]:

        def text(key, firm=firm):
            return escape(str(firm.get(key) or "Not specified"))

        links = "".join(
            f'<a href="{escape(url, quote=True)}" rel="noreferrer noopener" target="_blank">Additional source</a> '
            for url in firm.get("extra_sources", [])
        )
        cards.append(f'''<article><div class="eyebrow">{text("priority")} · Research qualified</div>
<h2>{text("name")}</h2><p>{text("evidence")}</p>
<dl><dt>Why assess fit</dt><dd>{text("fit_reason")}</dd>
<dt>Google Sheets evidence</dt><dd>{text("sheets_evidence")}</dd>
<dt>Buyer role</dt><dd>{text("buyer_role")}</dd>
<dt>Validate before a pilot</dt><dd>{text("validation_needed")}</dd></dl>
<footer>Retrieved {text("retrieved_on")} JST · Source updated/published {text("published_on")}<br>
<a href="{text("source_url")}" rel="noreferrer noopener" target="_blank">Primary source</a> {links}</footer></article>''')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sellbird · {escape(project["project"])}</title><link rel="stylesheet" href="/static/review.css"></head>
<body><header><span class="eyebrow">Sellbird / Projects</span><h1>{escape(project["project"])}</h1>
<p>{escape(project["product"])}</p><p class="offer">{escape(project["offer"])}</p>
<div class="status"><strong>{project["firm_count"]} firms</strong><span>Sending disabled</span><span>Autopilot disabled</span></div>
<p class="notice">Public evidence supports research fit. Buying intent, current tools, and pilot need require confirmation. No firms have been contacted through this project.</p></header>
<main>{"".join(cards)}</main><footer class="end">Evidence review only · Manual drafts require separate human review.</footer></body></html>"""


CSS = """*{box-sizing:border-box}body{margin:0;background:#eef2f8;color:#152b46;font:16px/1.6 system-ui,sans-serif}header,main,.end{max-width:1180px;margin:auto;padding:40px 28px}header{padding-bottom:16px}h1{font-size:64px;letter-spacing:-.05em;line-height:1.1;margin:12px 0 20px}h2{font-family:Georgia,serif;font-size:22px;line-height:1.4;margin:8px 0 18px}.eyebrow{font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:#526785}.offer{font-size:20px}.status{display:flex;gap:12px;flex-wrap:wrap;margin:24px 0}.status>*{background:#dce7f5;border-radius:5px;padding:5px 12px}.notice{max-width:850px;color:#526078}main{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:22px}article{background:#ffffff;border:1px solid #cbd7e7;border-radius:12px;padding:28px;overflow-wrap:anywhere}dl{margin:20px 0}dt{font-weight:650;font-size:13px;margin-top:16px;color:#405776}dd{margin:4px 0}footer{font-size:12px;color:#566780}a{color:#244f96;text-underline-offset:3px}a:focus-visible{outline:3px solid #244f96;outline-offset:4px}.end{text-align:center;padding-top:10px}@media(max-width:760px){main{grid-template-columns:1fr}h1{font-size:48px}header,main{padding:24px 18px}article{padding:22px}}"""


def build_review_app(
    database: Path, *, host: str, allowed_logins: list[str], whois=None
):
    app = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        middleware=[
            Middleware(
                TailnetGuard,
                host=host,
                allowed_logins=allowed_logins,
                whois=whois or TailnetWhois(),
            )
        ],
    )

    @app.get("/", response_class=HTMLResponse)
    def index():
        return render(read_project(database))

    @app.get("/static/review.css")
    def stylesheet():
        from fastapi.responses import Response

        return Response(CSS, media_type="text/css")

    @app.get("/healthz")
    def health():
        project = read_project(database)
        return {
            "status": "ok",
            "project": project["project"],
            "firms": project["firm_count"],
            "sending_enabled": False,
        }

    @app.get("/api/project")
    def project():
        result = read_project(database)
        return {key: value for key, value in result.items() if key != "firms"}

    @app.get("/api/companies")
    def companies():
        return read_project(database)["firms"]

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", type=Path, required=True)
    args = parser.parse_args()
    settings = read_private_json(args.settings)
    if set(settings) != {"database", "host", "allowed_logins", "port"}:
        raise ValueError("unexpected review settings")
    if (
        not isinstance(settings["allowed_logins"], list)
        or not settings["allowed_logins"]
    ):
        raise ValueError("requires private allowed operators")
    database = Path(settings["database"])
    project = read_project(database)
    if not project["firm_count"]:
        raise ValueError("project has no firms")
    import uvicorn

    uvicorn.run(
        build_review_app(
            database, host=settings["host"], allowed_logins=settings["allowed_logins"]
        ),
        host="127.0.0.1",
        port=int(settings["port"]),
        workers=1,
        access_log=False,
        log_level="warning",
        proxy_headers=False,
        server_header=False,
        limit_concurrency=32,
        timeout_keep_alive=5,
    )


if __name__ == "__main__":
    main()
