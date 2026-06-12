# V.E.G.A.R.D.
**Versatile Engine for General Answers, Reasoning & Dialogue**

A personal AI assistant running entirely on your own hardware — no cloud, no API bills, no data leaving your machine. Accessible through Discord, backed by a local LLM via [Ollama](https://ollama.com).

---

## Architecture

```
Ollama (local LLM on GPU)
  └── Odysseus Core  ─  FastAPI service (port 8000)
        └── Discord Bot  ─  discord.py client
```

The core and the bot are separate processes. The bot is a thin client — all AI logic lives in the core, making it easy to plug in other frontends later (web UI, CLI, etc.).

---

## Stack

| Layer | Tech |
|---|---|
| Discord bot | discord.py 2.x |
| Core API | FastAPI + uvicorn |
| AI backend | Ollama (LLaMA 3.1 8B by default) |
| HTTP client | httpx |

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
ODYSSEUS_URL=http://localhost:8000
OLLAMA_MODEL=llama3.1:8b
CHAT_CHANNEL_ID=your_channel_id   # free-chat channel, no command needed here
```

To get `CHAT_CHANNEL_ID`: Discord Settings → Advanced → enable **Developer Mode**, then right-click your channel → **Copy Channel ID**.

### 5. Run
Open two terminals:
```bash
# Terminal 1 — Odysseus core
python -m uvicorn core.main:app --reload

# Terminal 2 — Discord bot
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

### Core API endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Health check |
| `GET /models` | List available Ollama models |
| `POST /chat` | Send a message |
| `GET /chat/{user_id}/history` | Get history size |
| `DELETE /chat/{user_id}` | Clear history |

---

## Changing the model

Any model pulled in Ollama works. Update `OLLAMA_MODEL` in `.env` and restart the core.

```bash
ollama pull mistral
# then set OLLAMA_MODEL=mistral in .env
```
