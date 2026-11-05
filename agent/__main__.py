"""Command line: python -m agent <command>

  serve                         start the web UI (default)
  status                        check the LLM server
  chat                          talk to the agent in the terminal
  write  -p x,linkedin "brief"  write posts and save them as drafts
  research "topic"              sourced research brief
  calendar -p instagram,x --days 7 "theme"
  drafts [--status approved]    list drafts
  approve ID | publish ID       approve, then publish (respects dry_run)
"""

from __future__ import annotations

import argparse
import json
import sys

from . import agent, config, publishers, skills
from .llm import LLM, LLMError
from .store import Store


def _plats(s: str) -> list[str]:
    out = [p.strip().lower() for p in s.split(",") if p.strip()]
    unknown = [p for p in out if p not in config.platforms()]
    if unknown:
        sys.exit(f"unknown platform(s): {', '.join(unknown)}. Known: {', '.join(config.platforms())}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m agent", description="SocialAgent - local AI social media manager")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("serve"); s.add_argument("--host"); s.add_argument("--port", type=int)
    sub.add_parser("status")
    sub.add_parser("chat")
    s = sub.add_parser("write"); s.add_argument("brief"); s.add_argument("-p", "--platforms", default="x,linkedin")
    s.add_argument("--tone", default=""); s.add_argument("--research", action="store_true")
    s = sub.add_parser("research"); s.add_argument("topic")
    s = sub.add_parser("calendar"); s.add_argument("theme"); s.add_argument("-p", "--platforms", default="instagram,linkedin")
    s.add_argument("--days", type=int, default=7)
    s = sub.add_parser("drafts"); s.add_argument("--status")
    s = sub.add_parser("approve"); s.add_argument("id", type=int)
    s = sub.add_parser("publish"); s.add_argument("id", type=int)
    a = ap.parse_args(argv)

    if a.cmd in (None, "serve"):
        from .server import serve
        serve(getattr(a, "host", None), getattr(a, "port", None))
        return 0

    llm, store = LLM(), Store()
    try:
        if a.cmd == "status":
            print(json.dumps({"llm_url": llm.base_url, **llm.health()}, indent=2))
        elif a.cmd == "chat":
            history: list[dict] = []
            print("SocialAgent chat. Type 'exit' to quit.\n")
            while True:
                try:
                    q = input("you> ").strip()
                except (EOFError, KeyboardInterrupt):
                    break
                if q.lower() in ("exit", "quit"):
                    break
                if not q:
                    continue
                history.append({"role": "user", "content": q})
                res = agent.chat(history, llm, store, on_step=lambda t: print(f"  [tool] {t['tool']} {json.dumps(t['args'])[:100]}"))
                history.append({"role": "assistant", "content": res["reply"]})
                print(f"\nagent> {res['reply']}\n")
        elif a.cmd == "write":
            context = skills.research(llm, a.brief)["summary"] if a.research else ""
            for p in _plats(a.platforms):
                text = skills.write_post(llm, p, a.brief, context=context, tone=a.tone)
                d = store.add_draft(p, text, topic=a.brief[:200])
                print(f"\n--- draft #{d['id']} [{p}] ({skills.count_chars(text, p)} chars) ---\n{text}")
        elif a.cmd == "research":
            r = skills.research(llm, a.topic)
            print(r["summary"] + "\n\nSources:\n" + "\n".join(f"[{i + 1}] {s['title']} {s['url']}" for i, s in enumerate(r["sources"])))
        elif a.cmd == "calendar":
            for it in skills.content_calendar(llm, a.theme, a.days, _plats(a.platforms)):
                print(f"{it['date']}  {it['platform']:<10} {it['pillar']:<10} {it['format']:<10} {it['idea']}")
        elif a.cmd == "drafts":
            for d in store.list(a.status):
                print(f"#{d['id']:<4} {d['status']:<9} {d['platform']:<10} {d['scheduled_for'] or '-':<16} {d['text'][:70]!r}")
        elif a.cmd == "approve":
            print(store.update(a.id, status="approved")["status"])
        elif a.cmd == "publish":
            d = store.get(a.id)
            if not d:
                sys.exit(f"draft {a.id} not found")
            res = publishers.publish(d)
            if res.get("route") != "manual" and not res.get("dry_run"):
                store.update(a.id, status="published", result=json.dumps(res))
            store.log(a.id, "publish", json.dumps(res))
            print(json.dumps(res, indent=2))
    except (LLMError, publishers.PublishError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
