"""Paths and configuration. Everything lives next to the code, so the bundle is portable."""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(os.environ.get("SOCIAL_AGENT_HOME", Path(__file__).resolve().parent.parent))
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
WEB_DIR = Path(__file__).resolve().parent / "web"


def load_json(path: Path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        if default is not None:
            return default
        raise


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def settings() -> dict:
    s = load_json(CONFIG_DIR / "settings.json", {})
    # environment overrides, handy when the LLM runs on another machine
    if os.environ.get("SOCIAL_AGENT_LLM_URL"):
        s["llm_url"] = os.environ["SOCIAL_AGENT_LLM_URL"]
    return s


def brand() -> dict:
    return load_json(CONFIG_DIR / "brand.json", {})


def platforms() -> dict:
    return {k: v for k, v in load_json(CONFIG_DIR / "platforms.json", {}).items() if not k.startswith("_")}


def accounts() -> dict:
    data = load_json(CONFIG_DIR / "accounts.json", {})
    return {k: v for k, v in data.items() if not k.startswith("_") and isinstance(v, dict)}


def brand_brief(b: dict | None = None) -> str:
    b = b if b is not None else brand()
    if not b:
        return "No brand profile set."
    lines = [
        f"Brand: {b.get('name', '')} - {b.get('one_liner', '')}",
        f"Audience: {b.get('audience', '')}",
        f"Voice: {b.get('voice', '')}",
        f"Emoji use: {b.get('emoji', 'light')}",
        f"Language: {b.get('language', 'English')}",
    ]
    if b.get("always"):
        lines.append("Always: " + "; ".join(b["always"]))
    if b.get("never"):
        lines.append("Never: " + "; ".join(b["never"]))
    if b.get("default_hashtags"):
        lines.append("Brand hashtags (use when relevant): " + " ".join(b["default_hashtags"]))
    if b.get("website"):
        lines.append(f"Website: {b['website']}")
    return "\n".join(lines)
