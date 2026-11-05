# Running SocialAgent from a USB pen drive

## Choosing a drive

- **Size**: 16 GB or more. The model is about 4.7 GB, portable llama.cpp about 50–150 MB depending on the build, portable Python about 11 MB, plus your data.
- **Speed**: USB 3.0 or newer. The model is read once when it loads; on USB 2.0 that can take a few minutes.
- **Format**: **exFAT** works on Windows, macOS and Linux and supports files over 4 GB. FAT32 does not (4 GB per file limit). NTFS is fine for Windows-only use.

To format on Windows: File Explorer → right-click the drive → Format → File system: exFAT. (This erases the drive.)

## Two ways to run llama.cpp

| | Installed (default) | Portable (`-Portable`) |
|---|---|---|
| How | `winget install llama.cpp` on each PC | Setup downloads the official release into `bin\` on the drive |
| Needs admin / installs on the PC | winget install (per user) | Nothing installed on the PC |
| Best for | Your own PCs | Borrowed or locked-down PCs |

The start scripts look for `bin\llama-server.exe` on the drive first, then for `llama-server` installed with winget.

## Where things are stored

- The model is downloaded to `models\` on the drive because the scripts set `LLAMA_CACHE` there. Without the script, `llama-server -hf ...` stores it in your Windows user profile instead.
- Drafts and the posting log are in `data\agent.db` (SQLite).
- Nothing is written to the PC except the winget install (if you use it) and your browser's normal cache.

## Memory and speed

Qwen2.5-7B-Instruct Q4_K_M uses about 4.7 GB for the weights plus the context memory:

| Context (`-c`) | Approx. extra RAM | Use |
|---|---|---|
| `0` (model maximum, 32K) | ~1.8 GB | Default, as in the original command. Best for long research briefs |
| `8192` (`-LowMemory`) | ~0.5 GB | 8 GB RAM PCs |
| `4096` | ~0.25 GB | Very tight memory; research briefs get shorter |

Close browsers and other big apps on 8 GB machines. Speed depends mostly on CPU and memory bandwidth: expect about
3–10 tokens per second on a recent laptop CPU, and much faster with a GPU (`-Backend vulkan` at setup, then
`-GpuLayers 99`).

## Using it on several PCs

The drive letter can change from PC to PC; the scripts use paths relative to their own location, so that's fine.
If a PC blocks running scripts, `START-SocialAgent.bat` already uses `-ExecutionPolicy Bypass` for its own process
only. Some company PCs block USB drives or unknown executables entirely; ask IT, or run the agent on your own machine
and point `llm_url` at it.

## macOS and Linux

```bash
brew install llama.cpp            # macOS; on Linux build or download from github.com/ggml-org/llama.cpp
./start.sh                        # starts the LLM (model stored on the drive) and the agent
LOW_MEMORY=1 ./start.sh           # 8K context
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `llama-server` not recognised | Close and reopen PowerShell after `winget install llama.cpp`, or run setup with `-Portable` |
| Model download fails at ~4 GB | The drive is FAT32: reformat as exFAT |
| "Cannot reach the LLM" in the app | The LLM window must stay open; check it for errors. The first load can take minutes |
| Very slow answers | Use `-LowMemory`, close other apps, use a USB 3 port, or a GPU build |
| Web research returns nothing | DuckDuckGo may rate-limit; wait a minute, or set up SearXNG in `config/settings.json` |
| Port already in use | Change `--port`/`-Port` and `llm_url`, or `ui_port` in `config/settings.json` |
