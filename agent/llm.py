"""Client for llama.cpp's llama-server (OpenAI-compatible API) running Qwen2.5-7B-Instruct."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from . import config


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self, base_url: str | None = None, temperature: float | None = None, timeout: float | None = None):
        s = config.settings()
        self.base_url = (base_url or s.get("llm_url", "http://127.0.0.1:8034")).rstrip("/")
        self.temperature = s.get("llm_temperature", 0.7) if temperature is None else temperature
        self.timeout = timeout or s.get("llm_timeout_seconds", 900)

    def _post(self, path: str, payload: dict) -> dict:
        req = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:500]
            raise LLMError(f"LLM server returned {e.code}: {body}") from e
        except urllib.error.URLError as e:
            raise LLMError(
                f"Cannot reach the LLM at {self.base_url} ({e.reason}). Is llama-server running? "
                "Start it with scripts\\start-llm.ps1 (Windows) or scripts/start-llm.sh."
            ) from e

    def health(self) -> dict:
        try:
            with urllib.request.urlopen(self.base_url + "/health", timeout=5) as r:
                return {"ok": True, **json.loads(r.read().decode("utf-8") or "{}")}
        except urllib.error.HTTPError as e:  # 503 while the model is loading
            return {"ok": False, "status": "loading" if e.code == 503 else f"http {e.code}"}
        except Exception as e:
            return {"ok": False, "status": f"offline ({getattr(e, 'reason', e)})"}

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        json_schema: dict | None = None,
        max_tokens: int = 1500,
        temperature: float | None = None,
    ) -> dict:
        """Return the assistant message dict: {'role','content','tool_calls'?}."""
        payload: dict = {
            "model": "qwen2.5-7b-instruct",  # llama-server serves one model and ignores this
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
        if json_schema:
            payload["response_format"] = {"type": "json_schema", "json_schema": {"name": "out", "schema": json_schema}}
        data = self._post("/v1/chat/completions", payload)
        try:
            msg = data["choices"][0]["message"]
        except (KeyError, IndexError) as e:
            raise LLMError(f"Unexpected LLM response: {str(data)[:300]}") from e
        msg.setdefault("content", "")
        if msg["content"] is None:
            msg["content"] = ""
        if not msg.get("tool_calls"):
            parsed = parse_text_tool_calls(msg["content"])
            if parsed:
                msg["tool_calls"] = parsed
                msg["content"] = re.sub(r"<tool_call>.*?</tool_call>", "", msg["content"], flags=re.S).strip()
        return msg

    def text(self, system: str, user: str, max_tokens: int = 1500, temperature: float | None = None) -> str:
        msg = self.chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
                        max_tokens=max_tokens, temperature=temperature)
        return strip_think(msg["content"]).strip()

    def json(self, system: str, user: str, schema: dict, max_tokens: int = 2000) -> dict | list:
        msg = self.chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
                        json_schema=schema, max_tokens=max_tokens, temperature=0.4)
        return extract_json(msg["content"])


def strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)


def parse_text_tool_calls(content: str) -> list[dict]:
    """Qwen sometimes writes Hermes-style <tool_call>{...}</tool_call> in plain text; convert it."""
    calls = []
    for i, m in enumerate(re.finditer(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", content or "", re.S)):
        try:
            obj = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if "name" in obj:
            args = obj.get("arguments", {})
            calls.append({
                "id": f"call_text_{i}",
                "type": "function",
                "function": {"name": obj["name"], "arguments": json.dumps(args) if not isinstance(args, str) else args},
            })
    return calls


def extract_json(text: str):
    """Parse the first JSON object or array in model output (tolerates code fences and chatter)."""
    text = strip_think(text).strip()
    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start = text.find(open_c)
        while start != -1:
            depth, in_str, esc = 0, False, False
            for i in range(start, len(text)):
                c = text[i]
                if in_str:
                    if esc:
                        esc = False
                    elif c == "\\":
                        esc = True
                    elif c == '"':
                        in_str = False
                    continue
                if c == '"':
                    in_str = True
                elif c == open_c:
                    depth += 1
                elif c == close_c:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start: i + 1])
                        except json.JSONDecodeError:
                            break
            start = text.find(open_c, start + 1)
    raise LLMError("The model did not return valid JSON. Try again or simplify the request.")
