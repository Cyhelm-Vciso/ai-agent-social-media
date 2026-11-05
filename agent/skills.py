"""Social media manager skills. Each one is a short, focused prompt, which works well with a 7B model."""

from __future__ import annotations

import datetime as dt
import re

from . import config, tools
from .llm import LLM

URL_RE = re.compile(r"https?://\S+")

SYSTEM_BASE = """You are an expert social media manager and copywriter.
You write original, platform-native posts that sound human, never robotic.
Rules: never invent facts, statistics, quotes, prices, dates, or customer names. If something isn't in the brief or
sources, leave it out or write [ADD DETAIL] for the user to fill in. No clickbait that the content doesn't deliver.
{brand}"""


def system_prompt() -> str:
    return SYSTEM_BASE.format(brand=config.brand_brief())


def count_chars(text: str, platform: str) -> int:
    """Approximate the platform's own counter. X counts every link as 23 characters."""
    if platform == "x":
        return len(URL_RE.sub("x" * 23, text))
    return len(text)


def _clean(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```\w*\n?|\n?```$", "", text).strip()
    text = re.sub(r"^(?:here(?:'s| is)[^\n]*:\s*\n)", "", text, flags=re.I)  # drop "Here's your post:" preambles
    if len(text) > 1 and text[0] == text[-1] == '"':
        text = text[1:-1].strip()
    return text


def fit_to_limit(llm: LLM, text: str, platform: str, limit: int) -> str:
    """Ask the model to shorten an over-long post, then hard-trim at a sentence boundary as a last resort."""
    if count_chars(text, platform) <= limit:
        return text
    shorter = _clean(llm.text(
        system_prompt(),
        f"Shorten this {platform} post to at most {int(limit * 0.9)} characters. Keep the hook, the key point, and the "
        f"call to action. Return only the post.\n\n{text}",
        max_tokens=800, temperature=0.3,
    ))
    if shorter and count_chars(shorter, platform) <= limit:
        return shorter
    text = shorter or text
    cut = text[: limit - 1]
    for sep in ("\n", ". ", "! ", "? "):
        idx = cut.rfind(sep)
        if idx > limit * 0.5:
            return cut[: idx + 1].strip()
    return cut.rstrip() + "…"


def write_post(llm: LLM, platform: str, brief: str, context: str = "", tone: str = "") -> str:
    rules = config.platforms().get(platform)
    if not rules:
        raise ValueError(f"unknown platform '{platform}'. Known: {', '.join(config.platforms())}")
    user = (
        f"Write one {rules['name']} post.\n"
        f"Platform style: {rules['style']}\n"
        f"Length: at most {rules['max_chars']} characters. Hashtags: {rules['hashtags']}.\n"
        + (f"Tone for this post: {tone}\n" if tone else "")
        + f"\nBrief:\n{brief}\n"
        + (f"\nFacts and sources you may use (and only these):\n{context}\n" if context else "")
        + "\nReturn only the post text, ready to publish. No explanations, no quotes around it."
    )
    text = _clean(llm.text(system_prompt(), user, max_tokens=1200))
    return fit_to_limit(llm, text, platform, rules["max_chars"])


def research(llm: LLM, topic: str, max_sources: int = 4) -> dict:
    """Search the web, read the top pages, and write a sourced brief for content creation."""
    results = tools.web_search(topic)
    sources, notes = [], []
    for r in results:
        if len(sources) >= max_sources:
            break
        try:
            page = tools.fetch_page(r["url"], max_chars=3500)
        except Exception:
            continue
        if len(page["text"]) < 300:
            continue
        sources.append({"title": page["title"] or r["title"], "url": r["url"]})
        notes.append(f"[{len(sources)}] {page['title'] or r['title']} ({r['url']})\n{page['text']}")
    if not sources:
        notes = [f"[{i + 1}] {r['title']} ({r['url']})\n{r['snippet']}" for i, r in enumerate(results)]
        sources = [{"title": r["title"], "url": r["url"]} for r in results]
    if not notes:
        return {"topic": topic, "summary": "No search results found. Try a different query.", "sources": []}
    summary = llm.text(
        "You are a careful research assistant for a social media manager. Use only the sources provided. "
        "Cite sources as [1], [2]. If sources disagree or are thin, say so.",
        f"Topic: {topic}\n\nSources:\n\n" + "\n\n".join(notes) +
        "\n\nWrite a research brief with these sections:\n"
        "1. Key facts (bullets, each with a citation)\n"
        "2. What people are discussing or asking\n"
        "3. Five content angles we could post about\n"
        "4. Caveats (what to double-check before posting)",
        max_tokens=1500, temperature=0.3,
    )
    return {"topic": topic, "summary": summary, "sources": sources}


def repurpose(llm: LLM, source: str, platforms: list[str]) -> dict[str, str]:
    """Turn an article URL or pasted text into native posts for several platforms."""
    context, link = source, ""
    if re.match(r"^https?://\S+$", source.strip()):
        page = tools.fetch_page(source.strip(), max_chars=5000)
        link = source.strip()
        context = f"Title: {page['title']}\nURL: {link}\n\n{page['text']}"
    brief = "Repurpose the source below into a post for this platform. Pick the most interesting point for this audience."
    if link:
        brief += f" Include the link {link} where it fits the platform."
    return {p: write_post(llm, p, brief, context=context) for p in platforms}


CALENDAR_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "day": {"type": "integer"},
                    "platform": {"type": "string"},
                    "pillar": {"type": "string"},
                    "idea": {"type": "string"},
                    "format": {"type": "string"},
                },
                "required": ["day", "platform", "pillar", "idea", "format"],
            },
        }
    },
    "required": ["items"],
}


def content_calendar(llm: LLM, theme: str, days: int, platforms: list[str], start: dt.date | None = None) -> list[dict]:
    start = start or dt.date.today()
    data = llm.json(
        system_prompt(),
        f"Plan a {days}-day social media content calendar.\nTheme or goal: {theme}\n"
        f"Platforms: {', '.join(platforms)}\n"
        "Mix content pillars (educate, entertain, inspire, promote, community) and formats (text, image, carousel, "
        "short video, poll, thread). Promote at most one day in five. One item per platform per day.\n"
        "Return JSON: {\"items\": [{\"day\": 1, \"platform\": \"linkedin\", \"pillar\": \"educate\", "
        "\"idea\": \"...\", \"format\": \"carousel\"}]}",
        CALENDAR_SCHEMA, max_tokens=3000,
    )
    items = data.get("items", []) if isinstance(data, dict) else data
    known = set(config.platforms())
    out = []
    for it in items:
        if not isinstance(it, dict) or it.get("platform") not in known:
            continue
        day = max(1, min(days, int(it.get("day", 1) or 1)))
        it["date"] = (start + dt.timedelta(days=day - 1)).isoformat()
        out.append(it)
    return out


def reply_suggestions(llm: LLM, platform: str, original_post: str, comment: str) -> str:
    return _clean(llm.text(
        system_prompt(),
        f"Platform: {platform}\nOur post:\n{original_post}\n\nA follower commented:\n{comment}\n\n"
        "Write 3 alternative replies (numbered), each under 280 characters: one helpful, one warm and personal, one "
        "that moves the conversation forward. If the comment is a complaint, acknowledge it and offer to take it to DMs. "
        "If it is abusive or spam, reply only with: 'Suggest: hide or ignore this comment.'",
        max_tokens=700,
    ))


def hashtags(llm: LLM, topic: str, platform: str) -> str:
    rules = config.platforms().get(platform, {})
    return _clean(llm.text(
        system_prompt(),
        f"Suggest hashtags for a {rules.get('name', platform)} post about: {topic}\n"
        f"Recommended count: {rules.get('hashtags', '3-5')}. Give a short list mixing broad and niche tags, then one "
        "line on which to use. Don't invent trending claims.",
        max_tokens=300, temperature=0.5,
    ))
