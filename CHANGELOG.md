# Changelog

All notable changes to V.E.G.A.R.D. are documented here.

---

### v1.2.0 — 2026-06-25
- Added `/play`, `/skip`, `/stop`, `/loop`, `/queue` slash commands for music control
- `/play <song>` accepts song names or YouTube URLs; resolves and displays the actual track title
- `/queue` shows only songs queued via `/play` — Spotify comfort playlist stays private
- Loop modes: loop queue (default), loop song 🔂, off — toggle via now-playing button or `/loop`
- Now-playing embed has loop button that reflects the current mode and cycles on click
- Pre-fetched `/play` tracks skip a second yt-dlp lookup when they reach the front of the queue

### v1.1.0 — 2026-06-24
- Music player now acknowledges mood in chat ("putting on your playlist") when joining VC
- Fixed auto-search triggering on mood messages (sad/tired messages no longer run web search)
- Fixed YouTube stream compatibility: prefer webm/m4a formats, add User-Agent header to avoid 403s
- Now-playing embed shows YouTube thumbnail
- Support multiple chat channel IDs via comma-separated `CHAT_CHANNEL_ID` in `.env`
- Playlist queue auto-shuffles and loops when exhausted

### v1.0.0 — 2026-06-23
- Auto-search: bot now decides when to search the web without requiring `/search` — uses Ollama tool calling (llama3.1:8b native), shows `🔍 Searching for "..."` while fetching, then streams the answer
- `/search` command remains as an explicit override
- Mood-aware music player: bot detects emotional keywords (sad/tired/sedih/lelah/etc.) and auto-joins VC to play owner's Spotify playlist
- Bot self-deafens on join; Discord embed with Pause/Resume, Skip, Stop controls
- Persistent conversation history saved to `data/history.json` — survives restarts, capped at 20 messages per channel
- Switched web search from Serper to Tavily

### v0.9.0 — 2026-06-23
- Added voice channel integration — `/join` and `/leave` slash commands
- Speech-to-text via `faster-whisper` (Whisper `base` model, CPU, auto language detection)
- Text-to-speech via `edge-tts` (`id-ID-ArdiNeural` voice, configurable via `TTS_VOICE`)
- Silence detection: bot transcribes speech after 1.2s of silence, then replies in chat and speaks back in voice
- Patched `discord-ext-voice-recv` to support Discord's mandatory DAVE E2EE protocol using the `davey` library
- Graceful disconnect on shutdown — bot leaves voice channel cleanly on Ctrl+C

### v0.8.0 — 2026-06-19
- Added per-user rate limiting — 3s cooldown on chat messages, 15s cooldown on `/search`
- Rate limit warnings auto-delete after 3 seconds

### v0.7.0 — 2026-06-19
- Added `/search` slash command — searches the web via Serper (Google) and streams a summarized answer
- Added streaming responses — bot edits the message in real-time as tokens arrive, with sentence-boundary-aware update throttling

### v0.6.0 — 2026-06-19
- Added Regenerate button to every bot response — click to re-run the same message and get a different reply
- Button shows loading state ("Regenerating...") while waiting, then updates the original message in place

### v0.5.0 — 2026-06-17
- Removed FastAPI core and Odysseus integration — bot now calls Ollama directly via the `ollama` Python library
- Simpler architecture: one process, no HTTP intermediary, faster response times
- Switched default model to `llama3.1:8b` (Q4, GPU-only, ~4.7 GB VRAM)

### v0.4.0 — 2026-06-17
- Bot now detects current date and time and includes it in every response
- Added user recognition via `users.json` — bot knows who it's talking to and remembers personal notes about each person
- Language detection: bot now matches the language of the current message (English → English, Indonesian → Indonesian)
- Chat history is now shared per channel instead of per user — group conversations have shared context
- Messages prefixed with sender's display name so the bot knows who said what

### v0.3.0 — 2026-06-14
- Expanded fine-tuning dataset to 200 examples across 5 topic batches (Python, casual chat, web dev, university life, tech concepts)
- Exported fine-tuned `vegard` model to Ollama via GGUF (available as `OLLAMA_MODEL=vegard`)
- Added ChatML stop tokens to prevent token bleed from fine-tuned model
- Fixed language mixing bug — bot no longer adds parenthetical translations
- Fixed QLoRA training pipeline: import order, `max_length` rename, `--skip-merge` flag, f16 GGUF export

### v0.2.0 — 2026-06-13
- Added QLoRA fine-tuning pipeline (`finetune/train.py`, `finetune/export.py`)
- Added dataset generation prompt and initial 51-example training set
- Fixed PyArrow DLL crash on Windows (import order fix)

### v0.1.0 — Initial release
- Discord bot with dedicated chat channel and @mention support
- Per-user conversation history
- Slash commands: `/chat`, `/clear`, `/history`
- Ollama backend with configurable model via `.env`
