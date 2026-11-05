"""Chat agent: Qwen2.5-7B plans, calls tools, and drafts posts.

The agent can research and SAVE DRAFTS, but it cannot publish. Publishing always needs a person to approve
the draft in the Drafts tab (or with the CLI), so a model mistake never goes live on its own.
"""

from __future__ import annotations

import datetime as dt
import json

from . import config, skills, tools
from .llm import LLM, strip_think
from .store import Store

AGENT_SYSTEM = """You are SocialAgent, an AI social media manager working for the brand below.
You help plan content, research topics, write and improve posts for any platform, and manage drafts.
Today's date is {today}.

Tools:
- web_search: find current information. Use it before writing about news, trends, or facts you are unsure of.
- fetch_page: read a web page the user gives you or that you found.
- read_rss: read a news or blog feed.
- write_post: write a platform-native post (it applies the platform's length and style rules).
- save_draft: save a finished post to the Drafts queue. Save drafts when the user asks for posts.
- list_drafts: see existing drafts.

You cannot publish. Tell the user to review and approve drafts in the Drafts tab.
Never invent facts or statistics; cite URLs you used. Be concise. Supported platforms: {platforms}.

{brand}"""

TOOLS = [
    {"type": "function", "function": {
        "name": "web_search", "description": "Search the web. Returns titles, URLs and snippets.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "fetch_page", "description": "Read the main text of a web page.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {
        "name": "read_rss", "description": "Read the latest items of an RSS or Atom feed.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {
        "name": "write_post", "description": "Write a post for one platform following its length and style rules.",
        "parameters": {"type": "object", "properties": {
            "platform": {"type": "string", "description": "e.g. x, linkedin, instagram, facebook, threads, bluesky"},
            "brief": {"type": "string", "description": "What the post should say, including any facts and links to use"},
            "tone": {"type": "string"}},
            "required": ["platform", "brief"]}}},
    {"type": "function", "function": {
        "name": "save_draft", "description": "Save a finished post to the Drafts queue for human review.",
        "parameters": {"type": "object", "properties": {
            "platform": {"type": "string"}, "text": {"type": "string"},
            "scheduled_for": {"type": "string", "description": "Optional date/time, e.g. 2026-11-10 09:00"},
            "topic": {"type": "string"}},
            "required": ["platform", "text"]}}},
    {"type": "function", "function": {
        "name": "list_drafts", "description": "List drafts, optionally filtered by status (draft, approved, published).",
        "parameters": {"type": "object", "properties": {"status": {"type": "string"}}}}},
]


def run_tool(name: str, args: dict, llm: LLM, store: Store) -> str:
    try:
        if name == "web_search":
            return json.dumps(tools.web_search(args["query"]), ensure_ascii=False)
        if name == "fetch_page":
            return json.dumps(tools.fetch_page(args["url"]), ensure_ascii=False)
        if name == "read_rss":
            return json.dumps(tools.read_rss(args["url"]), ensure_ascii=False)
        if name == "write_post":
            text = skills.write_post(llm, args["platform"].lower(), args["brief"], tone=args.get("tone", ""))
            return json.dumps({"platform": args["platform"], "text": text,
                               "chars": skills.count_chars(text, args["platform"].lower())}, ensure_ascii=False)
        if name == "save_draft":
            platform = args["platform"].lower()
            if platform not in config.platforms():
                return json.dumps({"error": f"unknown platform {platform}"})
            d = store.add_draft(platform, args["text"], args.get("topic", ""), args.get("scheduled_for", ""))
            return json.dumps({"saved": True, "draft_id": d["id"], "status": d["status"]})
        if name == "list_drafts":
            rows = store.list(args.get("status") or None, limit=30)
            return json.dumps([{k: r[k] for k in ("id", "platform", "status", "scheduled_for", "text")} for r in rows],
                              ensure_ascii=False)
        return json.dumps({"error": f"unknown tool {name}"})
    except Exception as e:  # the model sees the error and can recover
        return json.dumps({"error": f"{type(e).__name__}: {e}"})


def chat(history: list[dict], llm: LLM | None = None, store: Store | None = None, on_step=None) -> dict:
    """Run one agent turn. history: [{'role':'user'|'assistant','content':...}]. Returns reply and tool trace."""
    llm = llm or LLM()
    store = store or Store()
    s = config.settings()
    system = AGENT_SYSTEM.format(today=dt.date.today().isoformat(), platforms=", ".join(config.platforms()),
                                 brand=config.brand_brief())
    messages = [{"role": "system", "content": system}] + [
        {"role": m["role"], "content": m["content"]} for m in history[-12:] if m.get("role") in ("user", "assistant")
    ]
    trace = []
    for _ in range(int(s.get("max_agent_steps", 6))):
        msg = llm.chat(messages, tools=TOOLS, max_tokens=1500)
        calls = msg.get("tool_calls") or []
        if not calls:
            return {"reply": strip_think(msg.get("content", "")).strip(), "trace": trace}
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for call in calls:
            fn = call.get("function", {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            result = run_tool(name, args, llm, store)
            trace.append({"tool": name, "args": args, "result": result[:600]})
            if on_step:
                on_step(trace[-1])
            messages.append({"role": "tool", "tool_call_id": call.get("id", name), "content": result[:8000]})
    final = llm.chat(messages + [{"role": "user", "content": "Summarise what you did and what the user should do next."}],
                     max_tokens=600)
    return {"reply": strip_think(final.get("content", "")).strip(), "trace": trace}
