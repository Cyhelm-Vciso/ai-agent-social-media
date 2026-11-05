# AI Agent – Social Media Manager (runs from a USB drive)

[![ci](https://github.com/Cyhelm-Vciso/ai-agent-social-media/actions/workflows/ci.yml/badge.svg)](https://github.com/Cyhelm-Vciso/ai-agent-social-media/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**SocialAgent** is a private, offline-first AI social media manager that you can carry on a USB pen drive.
Its "brain" is **Qwen2.5-7B-Instruct** (4-bit, Q4_K_M) running locally through **llama.cpp**: no cloud AI, no
subscription, and your drafts never leave your machine unless you choose to publish them.

It researches topics, writes platform-native posts, plans content calendars, repurposes articles, suggests replies
and hashtags, and publishes approved posts to any social network.

| | |
|---|---|
| **Writes for** | X, LinkedIn, Facebook, Instagram, Threads, Bluesky, Mastodon, TikTok (scripts), YouTube, Pinterest, Reddit, Telegram, Discord, WhatsApp. Add more in `config/platforms.json` |
| **Researches** | Web search (DuckDuckGo, no key needed, or your own SearXNG), reads pages and RSS feeds, writes sourced briefs with citations |
| **Plans** | 1–31 day content calendars across content pillars and formats; can write every post as a draft |
| **Publishes** | Directly to Mastodon, Bluesky, X, LinkedIn, Facebook Pages, Telegram and Discord; to *anything else* (Instagram, TikTok, YouTube, Pinterest, Threads…) through a Make / Zapier / n8n / Buffer webhook; or one click opens the platform's own post box with the text filled in |
| **Stays safe** | The AI can only save drafts. **Nothing is posted until you approve it**, and live posting is off (dry run) until you turn it on |
| **Needs** | Windows 10/11 (also macOS/Linux), 8 GB RAM (16 GB recommended), a 16 GB+ USB 3 drive formatted **exFAT**. No GPU needed |

---

## Quick start (Windows)

### 1. Install llama.cpp (once per PC)

Open **PowerShell** from the Start menu and install llama.cpp:

```powershell
winget install llama.cpp
```

### 2. Start the LLM

Close PowerShell, reopen it, then run:

```powershell
llama-server -hf Qwen/Qwen2.5-7B-Instruct-GGUF:Q4_K_M --jinja -c 0 --host 0.0.0.0 --port 8034
```

This uses Qwen 2.5 7B Instruct with 4-bit quantization (Q4_K_M) on port 8034. The first run downloads the model,
about 4.7 GB. To keep the model **on the USB drive** instead of the PC, start it with the bundled script, which sets
`LLAMA_CACHE` to the drive's `models` folder and runs the exact same command:

```powershell
E:\SocialAgent\scripts\start-llm.ps1
```

(Replace `E:` with your USB drive letter.)

### 3. Start the agent

Double-click **`START-SocialAgent.bat`** on the drive. It starts the LLM if it isn't running, waits for the model
to load, starts the agent, and opens **http://localhost:8035** in your browser.

> First time on a PC without Python? Double-click **`SETUP-Windows.bat`** once. It runs `winget install llama.cpp`,
> puts a small portable Python (~11 MB) on the drive, creates `config\accounts.json`, and pre-downloads the model.

---

## Put it on a USB pen drive

1. Format the drive as **exFAT** (FAT32 can't hold files over 4 GB). 16 GB or larger, USB 3 recommended.
2. Copy this repository to the drive, e.g. `E:\SocialAgent` ([download ZIP](https://github.com/Cyhelm-Vciso/ai-agent-social-media/archive/refs/heads/main.zip) and extract).
3. Run `SETUP-Windows.bat`. For a **fully portable** drive that works on PCs without installing anything, use:
   ```powershell
   E:\SocialAgent\SETUP-Windows.bat -Portable
   ```
   This downloads the official llama.cpp release into `bin\` on the drive instead of using winget.
4. On any PC: plug in, double-click `START-SocialAgent.bat`.

What ends up on the drive:

```
SocialAgent/
├─ START-SocialAgent.bat     double-click to run
├─ SETUP-Windows.bat         one-time setup
├─ start.sh                  macOS / Linux launcher
├─ agent/                    the agent (Python standard library only, no pip installs)
│  └─ web/index.html         the app UI (works offline)
├─ config/
│  ├─ settings.json          LLM URL, ports, dry_run, search provider
│  ├─ brand.json             your brand voice, audience, rules
│  ├─ platforms.json         per-platform limits and style (editable)
│  └─ accounts.json          your API tokens (created from accounts.example.json, never committed)
├─ models/                   Qwen2.5-7B GGUF (~4.7 GB, downloaded on first run)
├─ runtime/python/           portable Python (created by setup)
├─ bin/                      portable llama.cpp (with -Portable)
└─ data/                     drafts database, posting log
```

More detail, including performance tips: [docs/USB-GUIDE.md](docs/USB-GUIDE.md).

## Low-resource tips

| Situation | What to do |
|---|---|
| 8 GB RAM PC | `START-SocialAgent.bat -LowMemory`: uses an 8K context instead of the model's full 32K (`-c 0`), saving about 1.5 GB of RAM |
| Slow USB 2.0 drive | `START-SocialAgent.bat -NoMmap` loads the model fully into RAM once, instead of reading it from the drive during use |
| Has a GPU | Run setup with `-Portable -Backend vulkan`, then `START-SocialAgent.bat -GpuLayers 99` |
| Public Wi-Fi | `START-SocialAgent.bat -BindHost 127.0.0.1` so other devices on the network can't use your model (see Security below) |
| Even smaller | Use a 3B model: `-Model Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M` (faster, lower quality) |

Expect about 3–10 words per second on a typical laptop CPU; a post takes 20–90 seconds.

## Using the agent

- **Agent**: chat in plain English. *"Research what's new in plant-based protein this month, then write a LinkedIn post and an X thread opener and save them as drafts."* The agent searches, reads, writes, and saves drafts; it shows each tool it used.
- **Create**: write a brief, tick platforms, optionally "Research the web first". Or paste a blog URL to **repurpose** it into posts for every platform.
- **Research**: sourced brief with key facts, what people are asking, five content angles, and caveats to check.
- **Calendar**: plan 1–31 days across platforms, content pillars and formats; optionally write every post.
- **Drafts**: edit with a live character counter, set a schedule date, **Approve → Publish**, copy, open the platform's composer, mark as posted, or export everything to CSV (handy for Buffer or Hootsuite bulk upload).
- **Engage**: three reply options for a comment or DM, and hashtag suggestions.
- **Brand & accounts**: set your brand voice once; see which publishing route each platform uses.

Command line (no browser needed):

```bash
python run_agent.py write -p x,linkedin "We just launched our free budgeting template"
python run_agent.py research "AI tools for small restaurants"
python run_agent.py calendar -p instagram,tiktok --days 7 "summer menu launch"
python run_agent.py drafts
python run_agent.py approve 3
python run_agent.py publish 3
python run_agent.py chat
```

## Publishing to social networks

Copy `config/accounts.example.json` to `config/accounts.json` (setup does this) and fill in only the accounts you use.
Then set `"dry_run": false` in `config/settings.json` to post for real. Details for each network:
[docs/CONNECTORS.md](docs/CONNECTORS.md).

| Platform | Route | What you need |
|---|---|---|
| Mastodon | direct | Access token from your instance (Preferences → Development) |
| Bluesky | direct | Handle + an **app password** (Settings → App passwords) |
| X | direct | Developer app keys + user access token (OAuth 1.0a) |
| LinkedIn | direct | OAuth token with `w_member_social` and your person URN |
| Facebook Page | direct | Page ID + Page access token |
| Telegram | direct | Bot token + channel (bot must be an admin) |
| Discord | direct | Channel webhook URL |
| Instagram, TikTok, YouTube, Pinterest, Threads, … | webhook | A Make / Zapier / n8n / Buffer webhook that receives `{platform, text, scheduled_for}` |
| Anything | manual | Nothing: copy, or "Open in …" pre-fills the platform's own post box |

## Security

- The app listens on `127.0.0.1:8035` only, rejects requests from other websites (custom-header check), and blocks DNS-rebinding (Host check).
- The example LLM command uses `--host 0.0.0.0`, which lets **other devices on your network** use the model on port 8034. That's handy at home; on shared or public networks use `-BindHost 127.0.0.1`.
- `config/accounts.json` holds your tokens in plain text **on the USB drive**. Use app passwords and narrowly scoped tokens, never your main password, and revoke them if you lose the drive. Consider BitLocker To Go to encrypt the drive.
- The AI cannot publish. Approving is always a human step.

## Customise

- **Brand voice**: the Brand tab or `config/brand.json`.
- **Platforms**: add or edit entries in `config/platforms.json` (limit, hashtag count, style, compose link, route).
- **Search**: set `"provider": "searxng"` and `"searxng_url"` in `config/settings.json` to use your own SearXNG.
- **Another model**: any llama.cpp GGUF works; pass `-Model <hf-repo>:<quant>` to the start scripts.
- **LLM on another machine**: set `llm_url` in `config/settings.json`, e.g. `http://192.168.1.20:8034`.

## Development

```bash
python -m unittest discover -s tests -v    # no model or network needed; uses a mock llama-server
```

The agent uses only the Python standard library (3.10+), so it runs on the embeddable Python from the USB drive with
nothing to install.

## License

MIT. Qwen2.5-7B-Instruct is released by the Qwen team under the Apache 2.0 licence; llama.cpp is MIT. You are
responsible for following each social network's terms and automation rules.
