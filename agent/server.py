"""Local web UI + JSON API (standard library only).

Security: binds to 127.0.0.1 by default; every state-changing request must carry the
X-Requested-With: SocialAgent header (browsers block other sites from adding it without CORS approval,
which we never give), and the Host header must be localhost to block DNS-rebinding attacks.
"""

from __future__ import annotations

import csv
import io
import json
import mimetypes
import re
import sys
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import agent as agent_mod
from . import config, publishers, skills
from .llm import LLM, LLMError
from .store import Store

STORE: Store | None = None
ALLOWED_HOSTS: set[str] = set()


def _json_body(handler) -> dict:
    n = int(handler.headers.get("Content-Length") or 0)
    if n > 2_000_000:
        raise ValueError("request too large")
    raw = handler.rfile.read(n) if n else b"{}"
    return json.loads(raw.decode("utf-8") or "{}")


def _platform_list(value) -> list[str]:
    known = config.platforms()
    items = value if isinstance(value, list) else re.split(r"[,\s]+", str(value or ""))
    out = [p.strip().lower() for p in items if p and p.strip()]
    bad = [p for p in out if p not in known]
    if bad:
        raise ValueError(f"unknown platform(s): {', '.join(bad)}")
    if not out:
        raise ValueError("choose at least one platform")
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "SocialAgent/1.0"

    def log_message(self, fmt, *args):  # quieter console
        if not self.path.startswith("/api/status"):
            sys.stderr.write("  %s %s\n" % (self.command, self.path.split("?")[0]))

    # -- helpers -----------------------------------------------------------
    def _send(self, code: int, payload, ctype: str = "application/json; charset=utf-8"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").lower()
        return not ALLOWED_HOSTS or host in ALLOWED_HOSTS

    def _guard_write(self) -> bool:
        if self.headers.get("X-Requested-With") != "SocialAgent":
            self._send(403, {"error": "missing X-Requested-With header"})
            return False
        return True

    def _route(self, method: str):
        if not self._host_ok():
            return self._send(403, {"error": "bad Host header"})
        path = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(path.query)
        p = path.path.rstrip("/") or "/"
        try:
            if method != "GET" and not self._guard_write():
                return
            result = self._dispatch(method, p, qs)
            if result is not None:
                self._send(200, result)
        except (ValueError, KeyError) as e:
            self._send(400, {"error": str(e)})
        except LLMError as e:
            self._send(503, {"error": str(e)})
        except publishers.PublishError as e:
            self._send(502, {"error": str(e)})
        except Exception as e:  # pragma: no cover
            traceback.print_exc()
            self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def do_DELETE(self):
        self._route("DELETE")

    # -- routes ----------------------------------------------------------------
    def _dispatch(self, method: str, p: str, qs: dict):
        store = STORE
        if method == "GET" and p in ("/", "/index.html"):
            self._send(200, (config.WEB_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
            return None
        if method == "GET" and p.startswith("/static/"):
            f = (config.WEB_DIR / p[len("/static/"):]).resolve()
            if config.WEB_DIR.resolve() not in f.parents or not f.is_file():
                raise ValueError("not found")
            self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")
            return None

        if method == "GET" and p == "/api/status":
            return {"llm": LLM().health(), "llm_url": config.settings().get("llm_url"),
                    "dry_run": config.settings().get("dry_run", True),
                    "counts": {s: len(store.list(s, 1000)) for s in ("draft", "approved", "published", "failed")}}
        if method == "GET" and p == "/api/config":
            accounts = config.accounts()
            plats = config.platforms()
            return {
                "brand": config.brand(),
                "platforms": {k: {**v, "route": publishers.route_for(k, accounts)} for k, v in plats.items()},
                "accounts": {k: bool(v.get("enabled")) for k, v in accounts.items()},
                "dry_run": config.settings().get("dry_run", True),
            }
        if method == "POST" and p == "/api/brand":
            data = _json_body(self)
            if not isinstance(data, dict) or not data.get("name"):
                raise ValueError("brand must be an object with at least a name")
            config.save_json(config.CONFIG_DIR / "brand.json", data)
            return {"saved": True}

        llm = LLM()
        if method == "POST" and p == "/api/write":
            d = _json_body(self)
            brief = (d.get("brief") or "").strip()
            if not brief:
                raise ValueError("brief is required")
            platforms = _platform_list(d.get("platforms"))
            context, sources = "", []
            if d.get("research"):
                r = skills.research(llm, d.get("research_query") or brief)
                context, sources = r["summary"], r["sources"]
            drafts = []
            for plat in platforms:
                text = skills.write_post(llm, plat, brief, context=context, tone=d.get("tone", ""))
                drafts.append(store.add_draft(plat, text, topic=brief[:200], scheduled_for=d.get("scheduled_for", ""),
                                              sources=json.dumps(sources)))
            return {"drafts": drafts, "sources": sources}
        if method == "POST" and p == "/api/research":
            d = _json_body(self)
            if not d.get("topic"):
                raise ValueError("topic is required")
            return skills.research(llm, d["topic"])
        if method == "POST" and p == "/api/repurpose":
            d = _json_body(self)
            if not d.get("source"):
                raise ValueError("source (URL or text) is required")
            posts = skills.repurpose(llm, d["source"], _platform_list(d.get("platforms")))
            return {"drafts": [store.add_draft(k, v, topic="repurposed: " + d["source"][:150]) for k, v in posts.items()]}
        if method == "POST" and p == "/api/calendar":
            d = _json_body(self)
            days = max(1, min(31, int(d.get("days", 7))))
            items = skills.content_calendar(llm, d.get("theme") or "general brand awareness", days,
                                            _platform_list(d.get("platforms")))
            drafts = []
            if d.get("write"):
                for it in items:
                    text = skills.write_post(llm, it["platform"], f"{it['idea']} (format: {it['format']}, pillar: {it['pillar']})")
                    drafts.append(store.add_draft(it["platform"], text, topic=it["idea"], scheduled_for=it["date"]))
            return {"items": items, "drafts": drafts}
        if method == "POST" and p == "/api/reply":
            d = _json_body(self)
            return {"text": skills.reply_suggestions(llm, d.get("platform", "x"), d.get("post", ""), d["comment"])}
        if method == "POST" and p == "/api/hashtags":
            d = _json_body(self)
            return {"text": skills.hashtags(llm, d["topic"], d.get("platform", "instagram"))}
        if method == "POST" and p == "/api/chat":
            d = _json_body(self)
            history = d.get("history") or []
            if not history or history[-1].get("role") != "user":
                raise ValueError("history must end with a user message")
            return agent_mod.chat(history, llm=llm, store=store)

        # drafts
        if method == "GET" and p == "/api/drafts":
            return {"drafts": store.list((qs.get("status") or [None])[0])}
        if method == "GET" and p == "/api/history":
            return {"log": store.history()}
        if method == "GET" and p == "/api/export.csv":
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["id", "platform", "status", "scheduled_for", "text"])
            for r in store.list(limit=10000):
                w.writerow([r["id"], r["platform"], r["status"], r["scheduled_for"], r["text"]])
            self._send(200, buf.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8")
            return None
        m = re.fullmatch(r"/api/drafts/(\d+)(/publish|/compose)?", p)
        if m:
            draft_id, action = int(m.group(1)), m.group(2)
            draft = store.get(draft_id)
            if not draft:
                raise ValueError(f"draft {draft_id} not found")
            if method == "DELETE" and not action:
                store.delete(draft_id)
                return {"deleted": draft_id}
            if method == "GET" and action == "/compose":
                return {"url": publishers.compose_url(draft["platform"], draft["text"])}
            if method == "POST" and not action:
                d = _json_body(self)
                fields = {k: d[k] for k in ("text", "status", "scheduled_for") if k in d}
                if "status" in fields and fields["status"] == "published" and draft["status"] != "published":
                    fields["published_at"] = time.time()  # marked as posted manually
                return store.update(draft_id, **fields)
            if method == "POST" and action == "/publish":
                try:
                    result = publishers.publish(draft)
                except publishers.PublishError as e:
                    store.update(draft_id, result=str(e)[:1000])
                    store.log(draft_id, "publish_failed", str(e))
                    raise
                if result.get("route") != "manual" and not result.get("dry_run"):
                    store.update(draft_id, status="published", result=json.dumps(result),
                                 published_at=time.time())
                store.log(draft_id, "publish", json.dumps(result))
                return {"result": result, "draft": store.get(draft_id)}
        raise ValueError(f"unknown endpoint {method} {p}")


def serve(host: str | None = None, port: int | None = None) -> None:
    global STORE
    s = config.settings()
    host = host or s.get("ui_host", "127.0.0.1")
    port = int(port or s.get("ui_port", 8035))
    STORE = Store()
    if host in ("127.0.0.1", "localhost"):
        ALLOWED_HOSTS.update({f"127.0.0.1:{port}", f"localhost:{port}"})
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"\n  SocialAgent is running:  http://localhost:{port}\n  LLM: {s.get('llm_url')}   "
          f"dry_run={s.get('dry_run', True)}\n  Press Ctrl+C to stop.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
