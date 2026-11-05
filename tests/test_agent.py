"""Run with:  python -m unittest discover -s tests -v   (standard library only, no model needed)."""

import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent import agent as agent_mod  # noqa: E402
from agent import config, publishers, server, skills  # noqa: E402
from agent.llm import LLM, extract_json, parse_text_tool_calls  # noqa: E402
from agent.store import Store  # noqa: E402


# ---------------------------------------------------------------- mock llama-server

class MockLlama(BaseHTTPRequestHandler):
    """Behaves like llama-server: /health and /v1/chat/completions with simple scripted replies."""
    calls: list = []

    def log_message(self, *a):
        pass

    def _reply(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._reply({"status": "ok"})

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        MockLlama.calls.append(req)
        msgs = req["messages"]
        last = msgs[-1]["content"] if isinstance(msgs[-1].get("content"), str) else ""
        msg = {"role": "assistant", "content": ""}
        if req.get("tools"):
            if msgs[-1]["role"] == "user":
                msg["tool_calls"] = [{"id": "c1", "type": "function", "function": {
                    "name": "save_draft", "arguments": json.dumps({"platform": "x", "text": "Hello from the agent #test"})}}]
            else:
                msg["content"] = "Saved draft. Review it in the Drafts tab."
        elif "content calendar" in last:
            msg["content"] = json.dumps({"items": [
                {"day": 1, "platform": "x", "pillar": "educate", "idea": "Tip", "format": "text"},
                {"day": 2, "platform": "nope", "pillar": "x", "idea": "bad", "format": "text"}]})
        elif "Shorten" in last:
            msg["content"] = "Short version."
        elif "X (Twitter)" in last and "LONG" in last:
            msg["content"] = "word " * 200
        else:
            msg["content"] = "Here's your post:\nGreat news everyone! #launch"
        self._reply({"choices": [{"message": msg}]})


def start(handler):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(ROOT / "config", cls.tmp / "config")
        cls.llm_httpd = start(MockLlama)
        settings = json.loads((cls.tmp / "config" / "settings.json").read_text())
        settings["llm_url"] = f"http://127.0.0.1:{cls.llm_httpd.server_address[1]}"
        (cls.tmp / "config" / "settings.json").write_text(json.dumps(settings))
        cls._old = (config.CONFIG_DIR, config.DATA_DIR)
        config.CONFIG_DIR, config.DATA_DIR = cls.tmp / "config", cls.tmp / "data"

    @classmethod
    def tearDownClass(cls):
        config.CONFIG_DIR, config.DATA_DIR = cls._old
        cls.llm_httpd.shutdown()
        cls.llm_httpd.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)


# ---------------------------------------------------------------- unit tests

class ParsingTests(unittest.TestCase):
    def test_extract_json(self):
        self.assertEqual(extract_json('{"a": 1}'), {"a": 1})
        self.assertEqual(extract_json('Sure!\n```json\n{"a": "b}"}\n```'), {"a": "b}"})
        self.assertEqual(extract_json('x [1, 2] y'), [1, 2])
        self.assertEqual(extract_json('pre {"s": "quote \\" inside"} post'), {"s": 'quote " inside'})

    def test_text_tool_calls(self):
        calls = parse_text_tool_calls('<tool_call>\n{"name": "web_search", "arguments": {"query": "q"}}\n</tool_call>')
        self.assertEqual(calls[0]["function"]["name"], "web_search")
        self.assertEqual(json.loads(calls[0]["function"]["arguments"]), {"query": "q"})

    def test_x_counts_links_as_23(self):
        self.assertEqual(skills.count_chars("hi https://example.com/a/very/long/path/indeed", "x"), 3 + 23)
        self.assertEqual(skills.count_chars("hi https://e.co", "linkedin"), 15)


class PublisherTests(unittest.TestCase):
    def test_oauth1_signature_matches_twitter_docs_example(self):
        header = publishers.oauth1_header(
            "POST", "https://api.twitter.com/1.1/statuses/update.json",
            "xvz1evFS4wEEPTGEFPHBog", "kAcSOqF21Fu85e7zjz7ZN2U4ZRhfV3WpwPAoE3Z7kBw",
            "370773112-GmHxMAgYyLbNEtIKZeRNFsMKPR9EyMZeS9weJAEb", "LswwdoUaIvS8ltyTt5jkRh4J50vUPVVHtR2YPi5kE",
            extra_params={"status": "Hello Ladies + Gentlemen, a signed OAuth request!", "include_entities": "true"},
            nonce="kYjzVBB8Y0ZFabxSWbWovY3uYSQ2pTgmZeNu2VS4cg", timestamp="1318622958")
        self.assertIn('oauth_signature="hCtSmYh%2BiHYCEqBWrE7C7hYmtUk%3D"', header)

    def test_bluesky_facets_use_byte_offsets(self):
        text = "Héllo 🎉 #launch see https://ex.com/x."
        facets = publishers.bluesky_facets(text)
        raw = text.encode("utf-8")
        got = {f["features"][0]["$type"].split("#")[1]: raw[f["index"]["byteStart"]:f["index"]["byteEnd"]].decode() for f in facets}
        self.assertEqual(got, {"tag": "#launch", "link": "https://ex.com/x"})

    def test_linkedin_escape(self):
        self.assertEqual(publishers.linkedin_escape("Hi (all) #ai @me"), "Hi \\(all\\) \\#ai \\@me")


# ---------------------------------------------------------------- integration with mock LLM

class SkillTests(Base):
    def test_write_post_cleans_preamble(self):
        text = skills.write_post(LLM(), "linkedin", "launch")
        self.assertEqual(text, "Great news everyone! #launch")

    def test_fit_to_limit_shortens(self):
        text = skills.write_post(LLM(), "x", "LONG post please")
        self.assertEqual(text, "Short version.")

    def test_calendar_filters_unknown_platforms(self):
        items = skills.content_calendar(LLM(), "theme", 3, ["x"])
        self.assertEqual([i["platform"] for i in items], ["x"])
        self.assertIn("date", items[0])

    def test_agent_saves_draft_via_tool(self):
        store = Store(self.tmp / "data" / "t1.db")
        res = agent_mod.chat([{"role": "user", "content": "write an X post"}], LLM(), store)
        self.assertIn("Drafts", res["reply"])
        self.assertEqual(res["trace"][0]["tool"], "save_draft")
        self.assertEqual(store.list()[0]["platform"], "x")


class PublishFlowTests(Base):
    def test_requires_approval_then_dry_run_then_manual(self):
        store = Store(self.tmp / "data" / "t2.db")
        d = store.add_draft("x", "hello world")
        with self.assertRaises(publishers.PublishError):
            publishers.publish(d)
        d = store.update(d["id"], status="approved")
        res = publishers.publish(d)  # no accounts configured -> manual route with compose URL
        self.assertEqual(res["route"], "manual")
        self.assertTrue(res["compose_url"].startswith("https://x.com/intent/post?text=hello%20world"))
        config.save_json(config.CONFIG_DIR / "accounts.json", {"webhook": {"enabled": True, "url": "http://127.0.0.1:9/"}})
        try:
            res = publishers.publish(d)  # dry_run is true in settings.json
            self.assertTrue(res["dry_run"])
            self.assertEqual(res["route"], "webhook")
        finally:
            (config.CONFIG_DIR / "accounts.json").unlink()


class ServerTests(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        server.STORE = Store(cls.tmp / "data" / "srv.db")
        cls.httpd = start(server.Handler)
        cls.port = cls.httpd.server_address[1]
        server.ALLOWED_HOSTS.clear()
        server.ALLOWED_HOSTS.update({f"127.0.0.1:{cls.port}", f"localhost:{cls.port}"})

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        server.ALLOWED_HOSTS.clear()
        super().tearDownClass()

    def call(self, path, body=None, method=None, headers=None):
        h = {"X-Requested-With": "SocialAgent", "Content-Type": "application/json", **(headers or {})}
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method=method or ("POST" if body is not None else "GET"),
                                     data=json.dumps(body).encode() if body is not None else None, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_index_and_status(self):
        code, body = self.call("/")
        self.assertEqual(code, 200)
        self.assertIn(b"SocialAgent", body)
        code, body = self.call("/api/status")
        self.assertTrue(json.loads(body)["llm"]["ok"])

    def test_write_approve_publish_flow(self):
        code, body = self.call("/api/write", {"brief": "launch", "platforms": ["linkedin", "bluesky"]})
        self.assertEqual(code, 200, body)
        drafts = json.loads(body)["drafts"]
        self.assertEqual(len(drafts), 2)
        did = drafts[0]["id"]
        code, _ = self.call(f"/api/drafts/{did}/publish", {})
        self.assertEqual(code, 502)  # not approved
        self.call(f"/api/drafts/{did}", {"status": "approved"})
        code, body = self.call(f"/api/drafts/{did}/publish", {})
        self.assertEqual(json.loads(body)["result"]["route"], "manual")
        code, body = self.call("/api/export.csv")
        self.assertIn(b"linkedin", body)

    def test_csrf_and_host_guards(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/brand", data=b"{}", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 403)
        code, _ = self.call("/api/status", headers={"Host": "evil.example:80"})
        self.assertEqual(code, 403)

    def test_bad_platform_is_400(self):
        code, body = self.call("/api/write", {"brief": "x", "platforms": ["myspace"]})
        self.assertEqual(code, 400)
        self.assertIn(b"unknown platform", body)


if __name__ == "__main__":
    unittest.main()
