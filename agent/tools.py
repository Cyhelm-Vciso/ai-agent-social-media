"""Research tools: web search, page reading, and RSS. Standard library only, no API keys needed."""

from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

from . import config

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SocialAgent/1.0"


def _get(url: str, data: bytes | None = None, timeout: float = 20, headers: dict | None = None) -> str:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(3_000_000)
        charset = r.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, "replace")


# --- search ------------------------------------------------------------------


class _DDGParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results: list[dict] = []
        self._field: str | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "") or ""
        if tag == "a" and "result__a" in cls:
            self.results.append({"title": "", "url": _ddg_url(a.get("href", "")), "snippet": ""})
            self._field = "title"
        elif tag in ("a", "div") and "result__snippet" in cls and self.results:
            self._field = "snippet"

    def handle_endtag(self, tag):
        if tag in ("a", "div"):
            self._field = None

    def handle_data(self, data):
        if self._field and self.results:
            self.results[-1][self._field] += data


def _ddg_url(href: str) -> str:
    if "uddg=" in href:
        q = urllib.parse.urlparse(href if href.startswith("http") else "https:" + href).query
        return urllib.parse.parse_qs(q).get("uddg", [href])[0]
    return "https:" + href if href.startswith("//") else href


def web_search(query: str, max_results: int | None = None) -> list[dict]:
    s = config.settings().get("search", {})
    n = max_results or s.get("max_results", 6)
    if s.get("provider") == "searxng" and s.get("searxng_url"):
        url = s["searxng_url"].rstrip("/") + "/search?" + urllib.parse.urlencode({"q": query, "format": "json"})
        data = json.loads(_get(url))
        return [{"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
                for r in data.get("results", [])[:n]]
    body = urllib.parse.urlencode({"q": query}).encode()
    page = _get("https://html.duckduckgo.com/html/", data=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"})
    p = _DDGParser()
    p.feed(page)
    out = []
    for r in p.results:
        if r["url"].startswith("http") and "duckduckgo.com/y.js" not in r["url"]:
            out.append({k: re.sub(r"\s+", " ", html.unescape(v)).strip() for k, v in r.items()})
        if len(out) >= n:
            break
    return out


# --- page reading ------------------------------------------------------------


class _TextParser(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form", "aside"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in ("p", "br", "li", "h1", "h2", "h3", "h4", "tr", "div", "section", "article"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def fetch_page(url: str, max_chars: int | None = None) -> dict:
    if not re.match(r"^https?://", url):
        raise ValueError("only http(s) URLs are supported")
    max_chars = max_chars or config.settings().get("fetch_max_chars", 6000)
    raw = _get(url)
    p = _TextParser()
    p.feed(raw)
    text = re.sub(r"[ \t\r\f\v]+", " ", "".join(p.parts))
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return {"url": url, "title": p.title.strip(), "text": text[:max_chars], "truncated": len(text) > max_chars}


def read_rss(url: str, limit: int = 10) -> list[dict]:
    raw = _get(url)
    # Feeds never need entity declarations; refusing them blocks entity-expansion (billion laughs) and XXE tricks.
    if re.search(r"<!ENTITY", raw, re.I):
        raise ValueError("feed declares XML entities; refusing to parse it")
    root = ET.fromstring(raw.encode("utf-8"))
    items = []
    for it in root.iter():
        tag = it.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        get = lambda name: next((c for c in it if c.tag.split("}")[-1] == name), None)  # noqa: E731
        title = get("title")
        link = get("link")
        summary = get("description") or get("summary")
        date = get("pubDate") or get("updated") or get("published")
        href = (link.get("href") or link.text) if link is not None else ""
        items.append({
            "title": (title.text or "").strip() if title is not None else "",
            "url": (href or "").strip(),
            "summary": re.sub(r"<[^>]+>", "", html.unescape(summary.text or ""))[:300].strip() if summary is not None else "",
            "date": (date.text or "").strip() if date is not None else "",
        })
        if len(items) >= limit:
            break
    return items
