"""Publishing connectors. Standard library only.

Direct:   Mastodon, Bluesky, X, LinkedIn, Facebook Page, Telegram channel, Discord webhook.
Bridge:   'webhook' sends approved posts to Make, Zapier, n8n, IFTTT or Buffer, which reach Instagram, TikTok,
          YouTube, Pinterest, Threads and the rest.
Manual:   every platform with a compose URL can open its own post box with the text filled in.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config


class PublishError(RuntimeError):
    pass


def _request(url: str, method: str = "POST", json_body=None, form: dict | None = None, headers: dict | None = None,
             timeout: float = 30) -> dict:
    headers = dict(headers or {})
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    elif form is not None:
        data = urllib.parse.urlencode(form).encode("utf-8")
        headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    headers.setdefault("User-Agent", "SocialAgent/1.0")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
            return {"status": r.status, "body": json.loads(body) if body.strip().startswith(("{", "[")) else body,
                    "headers": dict(r.headers)}
    except urllib.error.HTTPError as e:
        raise PublishError(f"HTTP {e.code} from {urllib.parse.urlparse(url).netloc}: "
                           f"{e.read().decode('utf-8', 'replace')[:400]}") from e
    except urllib.error.URLError as e:
        raise PublishError(f"network error: {e.reason}") from e


# --- Mastodon ----------------------------------------------------------------

def post_mastodon(acc: dict, text: str) -> dict:
    r = _request(acc["instance"].rstrip("/") + "/api/v1/statuses", form={"status": text},
                 headers={"Authorization": f"Bearer {acc['access_token']}",
                          "Idempotency-Key": hashlib.sha256(text.encode()).hexdigest()})
    return {"id": r["body"].get("id"), "url": r["body"].get("url")}


# --- Bluesky (AT Protocol) -------------------------------------------------------

def bluesky_facets(text: str) -> list[dict]:
    """Make links and hashtags clickable. Bluesky facets use UTF-8 byte offsets."""
    facets = []

    def byte_span(start: int, end: int) -> dict:
        return {"byteStart": len(text[:start].encode("utf-8")), "byteEnd": len(text[:end].encode("utf-8"))}

    for m in re.finditer(r"https?://[^\s)\]]+", text):
        url = m.group(0).rstrip(".,;:!?")
        facets.append({"index": byte_span(m.start(), m.start() + len(url)),
                       "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}]})
    for m in re.finditer(r"(?:^|\s)(#[^\d\s#][^\s#]*)", text):
        tag = m.group(1).rstrip(".,;:!?")
        start = m.start(1)
        facets.append({"index": byte_span(start, start + len(tag)),
                       "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": tag[1:]}]})
    return facets


def post_bluesky(acc: dict, text: str) -> dict:
    service = acc.get("service", "https://bsky.social").rstrip("/")
    sess = _request(service + "/xrpc/com.atproto.server.createSession",
                    json_body={"identifier": acc["handle"], "password": acc["app_password"]})["body"]
    record = {"$type": "app.bsky.feed.post", "text": text,
              "createdAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"}
    facets = bluesky_facets(text)
    if facets:
        record["facets"] = facets
    r = _request(service + "/xrpc/com.atproto.repo.createRecord",
                 json_body={"repo": sess["did"], "collection": "app.bsky.feed.post", "record": record},
                 headers={"Authorization": f"Bearer {sess['accessJwt']}"})["body"]
    rkey = r.get("uri", "").rsplit("/", 1)[-1]
    return {"uri": r.get("uri"), "url": f"https://bsky.app/profile/{acc['handle']}/post/{rkey}"}


# --- X (Twitter) API v2 with OAuth 1.0a user context ---------------------------------

def _pct(s: str) -> str:
    return urllib.parse.quote(str(s), safe="~-._")


def oauth1_header(method: str, url: str, consumer_key: str, consumer_secret: str, token: str, token_secret: str,
                  extra_params: dict | None = None, nonce: str | None = None, timestamp: str | None = None) -> str:
    """RFC 5849 HMAC-SHA1 signature. JSON request bodies are not part of the signature."""
    oauth = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": nonce or secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": timestamp or str(int(time.time())),
        "oauth_token": token,
        "oauth_version": "1.0",
    }
    params = {**(extra_params or {}), **oauth}
    pairs = sorted((_pct(k), _pct(v)) for k, v in params.items())
    param_str = "&".join(f"{k}={v}" for k, v in pairs)
    base = "&".join([method.upper(), _pct(url), _pct(param_str)])
    key = f"{_pct(consumer_secret)}&{_pct(token_secret)}"
    oauth["oauth_signature"] = base64.b64encode(hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()).decode()
    return "OAuth " + ", ".join(f'{_pct(k)}="{_pct(v)}"' for k, v in sorted(oauth.items()))


def post_x(acc: dict, text: str) -> dict:
    url = "https://api.x.com/2/tweets"
    auth = oauth1_header("POST", url, acc["consumer_key"], acc["consumer_secret"], acc["access_token"],
                         acc["access_token_secret"])
    r = _request(url, json_body={"text": text}, headers={"Authorization": auth})["body"]
    tid = (r.get("data") or {}).get("id")
    return {"id": tid, "url": f"https://x.com/i/web/status/{tid}" if tid else None}


# --- LinkedIn (Posts API) ----------------------------------------------------------

_LINKEDIN_RESERVED = re.compile(r"([\\|{}@\[\]()<>#*_~])")


def linkedin_escape(text: str) -> str:
    """LinkedIn 'little text' treats these characters as markup; escape them so text posts verbatim."""
    return _LINKEDIN_RESERVED.sub(r"\\\1", text)


def post_linkedin(acc: dict, text: str) -> dict:
    body = {
        "author": acc["author_urn"],
        "commentary": linkedin_escape(text),
        "visibility": "PUBLIC",
        "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    r = _request("https://api.linkedin.com/rest/posts", json_body=body, headers={
        "Authorization": f"Bearer {acc['access_token']}",
        "LinkedIn-Version": str(acc.get("api_version", "202510")),
        "X-Restli-Protocol-Version": "2.0.0",
    })
    post_id = r["headers"].get("x-restli-id") or r["headers"].get("X-RestLi-Id")
    return {"id": post_id, "url": f"https://www.linkedin.com/feed/update/{post_id}" if post_id else None}


# --- Facebook Page -------------------------------------------------------------

def post_facebook(acc: dict, text: str) -> dict:
    ver = acc.get("graph_version", "v21.0")
    r = _request(f"https://graph.facebook.com/{ver}/{acc['page_id']}/feed",
                 form={"message": text, "access_token": acc["page_access_token"]})["body"]
    return {"id": r.get("id"), "url": f"https://www.facebook.com/{r.get('id')}" if r.get("id") else None}


# --- Telegram / Discord / generic webhook ----------------------------------------------

def post_telegram(acc: dict, text: str) -> dict:
    r = _request(f"https://api.telegram.org/bot{acc['bot_token']}/sendMessage",
                 json_body={"chat_id": acc["chat_id"], "text": text})["body"]
    return {"id": (r.get("result") or {}).get("message_id")}


def post_discord(acc: dict, text: str) -> dict:
    _request(acc["webhook_url"], json_body={"content": text[:2000]})
    return {"ok": True}


def post_webhook(acc: dict, text: str, platform: str = "", draft: dict | None = None) -> dict:
    headers = {}
    if acc.get("secret_header"):
        headers[acc["secret_header"]] = acc.get("secret_value", "")
    payload = {"platform": platform, "text": text, "draft_id": (draft or {}).get("id"),
               "scheduled_for": (draft or {}).get("scheduled_for", ""), "source": "social-agent"}
    r = _request(acc["url"], json_body=payload, headers=headers)
    return {"ok": True, "status": r["status"]}


DIRECT = {
    "mastodon": post_mastodon, "bluesky": post_bluesky, "x": post_x, "linkedin": post_linkedin,
    "facebook": post_facebook, "telegram": post_telegram, "discord": post_discord,
}


def compose_url(platform: str, text: str) -> str:
    tpl = config.platforms().get(platform, {}).get("compose_url", "")
    if not tpl:
        return ""
    title, _, rest = text.partition("\n")
    return tpl.replace("{text}", urllib.parse.quote(text)).replace("{title}", urllib.parse.quote(title))


def route_for(platform: str, accounts: dict | None = None) -> str:
    """Which connector will be used: a direct API, the webhook bridge, or manual."""
    accounts = accounts if accounts is not None else config.accounts()
    pub = config.platforms().get(platform, {}).get("publisher", "manual")
    if pub in DIRECT and accounts.get(pub, {}).get("enabled"):
        return pub
    if accounts.get("webhook", {}).get("enabled"):
        return "webhook"
    return "manual"


def publish(draft: dict, dry_run: bool | None = None) -> dict:
    """Publish an APPROVED draft. Returns a result dict; raises PublishError on failure."""
    if draft["status"] != "approved":
        raise PublishError("Only approved drafts can be published. Approve it first.")
    dry_run = config.settings().get("dry_run", True) if dry_run is None else dry_run
    accounts = config.accounts()
    platform = draft["platform"]
    route = route_for(platform, accounts)
    if route == "manual":
        url = compose_url(platform, draft["text"])
        return {"route": "manual", "compose_url": url,
                "message": "No connector configured: copy the text or open the compose link to post it yourself."}
    if dry_run:
        return {"route": route, "dry_run": True,
                "message": f"Dry run: would post {len(draft['text'])} characters to {platform} via {route}. "
                           "Set \"dry_run\": false in config/settings.json to post for real."}
    acc = accounts[route]
    if route == "webhook":
        return {"route": route, **post_webhook(acc, draft["text"], platform, draft)}
    return {"route": route, **DIRECT[route](acc, draft["text"])}
