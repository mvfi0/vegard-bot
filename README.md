# V.E.G.A.R.D.
**Versatile Engine for General Answers, Reasoning & Dialogue**

A personal AI assistant running entirely on your own hardware — no cloud, no API bills, no data leaving your machine. Accessible through Discord, backed by a local LLM via [Ollama](https://ollama.com).

---

## Architecture

```
Discord
  └── Bot (discord.py)
        └── OllamaService (Python)
              └── Ollama (local LLM on GPU)
```

The bot calls Ollama directly via the `ollama` Python library. No intermediary service — simple, fast, and everything runs on your machine.

---

## Stack

| Layer | Tech |
|---|---|
| Discord bot | discord.py 2.x |
| AI backend | Ollama (LLaMA 3.1 8B by default) |
| Ollama client | ollama-python |

---

## Setup

### 1. Prerequisites
- Python 3.11+
- [Ollama](https://ollama.com/download) installed and running
- A Discord bot token from the [Discord Developer Portal](https://discord.com/developers/applications)

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Pull the model
```bash
ollama pull llama3.1:8b
```

### 4. Configure environment
```bash
cp .env.example .env
```
Fill in `.env`:
```env
DISCORD_TOKEN=your_bot_token
OLLAMA_MODEL=llama3.1:8b
CHAT_CHANNEL_ID=your_channel_id   # free-chat channel, no command needed here
```

To get `CHAT_CHANNEL_ID`: Discord Settings → Advanced → enable **Developer Mode**, then right-click your channel → **Copy Channel ID**.

### 5. Run
```bash
python main.py
```

### 6. Invite the bot
OAuth2 → URL Generator → scopes: `bot` + `applications.commands` → permissions: `Send Messages`, `Read Message History`, `View Channels`.

---

## Usage

| Where | How |
|---|---|
| Dedicated chat channel | Just type — no command needed |
| Any other channel | @mention the bot or use `/chat` |

### Slash commands

| Command | Description |
|---|---|
| `/chat <message>` | Chat with V.E.G.A.R.D. |
| `/clear` | Clear your conversation history |
| `/history` | Check how many messages are in your history |

---

## Changelog

### v0.7.0 — 2026-06-19
- Added `/search` slash command — searches the web via Serper (Google) and streams a summarized answer
- Added streaming responses — bot edits the message in real-time as tokens arrive, with sentence-boundary-aware update throttling
- Added Regenerate button to every response — re-runs the same message and edits the reply in place with loading state

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
- FastAPI core (Odysseus) with per-user conversation history
- Slash commands: `/chat`, `/clear`, `/history`
- Ollama backend with configurable model via `.env`

---

## Changing the model

Any model pulled in Ollama works. Update `OLLAMA_MODEL` in `.env` and restart the bot.

```bash
ollama pull mistral
# then set OLLAMA_MODEL=mistral in .env
```
