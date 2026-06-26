import asyncio
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

import ollama
from .history import HistoryManager
from services.search import web_search

_HISTORY_PATH = Path(__file__).parent.parent.parent / "data" / "history.json"

_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the web for real-time or time-sensitive information: current news, "
            "today's weather, live prices, recent events, or specific facts that may have "
            "changed since your training cutoff. "
            "Do NOT call this for casual chat, greetings, opinions, code help, math, "
            "or anything you can answer from existing knowledge. "
            "When in doubt, do NOT call this."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
            },
            "required": ["query"],
        },
    },
}

# Keywords that suggest the message might need real-time info.
# If none of these appear, skip the tool-check round-trip entirely.
_SEARCH_HINTS = {
    "news", "weather", "temperature", "forecast", "rain", "score", "result",
    "price", "cost", "rate", "stock", "crypto", "bitcoin", "ethereum",
    "today", "tonight", "yesterday", "tomorrow", "now", "current", "currently",
    "latest", "recent", "recently", "right now", "at the moment",
    "this week", "this month", "this year", "2025", "2026",
    "who won", "who is", "what happened", "what's happening",
    "breaking", "update", "released", "announced", "launched",
    "lyrics", "lirik",
}

# Short confirmations that mean "yes, do the thing you just offered"
_CONFIRMATIONS = {"sure", "yes", "yeah", "yep", "yup", "ok", "okay", "go ahead",
                  "please", "do it", "go for it", "why not", "iya", "boleh"}

# Phrases in the bot's last reply that indicate it offered to search
_SEARCH_OFFER_PHRASES = (
    "web search", "search if you", "quick search", "look it up",
    "look up", "find out", "search for", "i can search",
)


def _needs_search_check(text: str, last_assistant: str = "") -> bool:
    """Return True if the message should go through the tool-check pass."""
    lower = text.lower()
    # Direct search keywords in the current message
    if any(hint in lower for hint in _SEARCH_HINTS):
        return True
    # User confirming a search the bot just offered
    words = set(lower.split())
    if words & _CONFIRMATIONS:
        return any(phrase in last_assistant.lower() for phrase in _SEARCH_OFFER_PHRASES)
    return False

SYSTEM_PROMPT = """\
You are V.E.G.A.R.D. — Versatile Engine for General Answers, Reasoning & Dialogue.
You are the personal AI of Muhammad Vegard, running fully local on his own hardware. No cloud, no corporate overlords.

Who you're talking to:
- Muhammad Vegard — call him Vegard, or just "bro"
- University student who codes. Don't over-explain technical stuff, he gets it
- Treat him like a close, slightly nerdy friend

How you talk:
- Casual and direct — like texting a friend, not writing a corporate email
- Occasionally dry or sarcastic, never mean
- Skip filler: no "Certainly!", no "Great question!", no "As an AI..."
- Short by default. Go longer only when the task actually needs it
- If you don't know something, say so

CRITICAL — Language detection (highest priority rule):
- Look at the actual words in the latest message. If those words are English → your entire reply must be in English. No Indonesian words at all.
- If those words are Indonesian or Indonesian slang → your entire reply must be in Indonesian. No English words at all.
- Do NOT use the person's name or past conversation to decide language. Only the current message text matters.
- NEVER add parenthetical translations like "(No wonder...)" — one language per reply, always.
- When replying in Indonesian: pronouns are gue (I/me) and lu (you). NEVER use kamu, anda, aku, or saya. If you catch yourself about to write "kamu", write "lu" instead. No exceptions.

Identity:
- You are V.E.G.A.R.D., an AI. You are NOT a human and you are NOT any of the people mentioned in the background info.
- You were built by Vegard (Muhammad Vegard Fathul Islam). He coded you, runs you on his own machine.
- If anyone asks who made you or who created you, say Vegard built you.
- If someone asks about a person by name (e.g. "who is Gabriel?"), look them up in the background info and describe them — do not say that person is you.

You run on his machine. What's said here stays here.

Tool use:
- Only call web_search when the message explicitly asks for something real-time or time-sensitive (current news, live prices, today's weather, recent events).
- Never call web_search for greetings, casual chat, coding questions, math, opinions, or anything you already know.\
"""


class OllamaService:
    def __init__(self, model: str):
        self.model = model
        self._client = ollama.AsyncClient()
        self.history = HistoryManager(persist_path=_HISTORY_PATH)

    async def chat(self, user_id: str, message: str, context: str | None = None, model: str | None = None) -> str:
        self.history.append(user_id, "user", message)

        now = datetime.now().strftime("%A, %d %B %Y, %H:%M")
        system = f"{SYSTEM_PROMPT}\n\nCurrent date and time: {now}"
        if context:
            system = f"{system}\n\n{context}"
        messages = [
            {"role": "system", "content": system},
            *self.history.get(user_id),
        ]

        response = await self._client.chat(
            model=model or self.model,
            messages=messages,
            options={"stop": ["<|im_start|>", "<|im_end|>", "<|im_start|>system"]},
        )
        reply: str = response.message.content

        # Strip any ChatML tokens that slipped through
        for token in ("<|im_start|>system", "<|im_start|>", "<|im_end|>"):
            reply = reply.replace(token, "")
        reply = reply.strip()

        self.history.append(user_id, "assistant", reply)
        return reply

    async def stream_chat(
        self, user_id: str, message: str, context: str | None = None, model: str | None = None
    ) -> AsyncGenerator[str, None]:
        self.history.append(user_id, "user", message)

        now = datetime.now().strftime("%A, %d %B %Y, %H:%M")
        system = f"{SYSTEM_PROMPT}\n\nCurrent date and time: {now}"
        if context:
            system = f"{system}\n\n{context}"
        messages = [
            {"role": "system", "content": system},
            *self.history.get(user_id),
        ]

        _model = model or self.model
        accumulated = ""
        async for chunk in await self._client.chat(
            model=_model,
            messages=messages,
            options={"stop": ["<|im_start|>", "<|im_end|>", "<|im_start|>system"]},
            stream=True,
        ):
            accumulated += chunk.message.content or ""
            clean = accumulated
            for tok in ("<|im_start|>system", "<|im_start|>", "<|im_end|>"):
                clean = clean.split(tok)[0]
            yield clean

        final = accumulated
        for tok in ("<|im_start|>system", "<|im_start|>", "<|im_end|>"):
            final = final.split(tok)[0]
        self.history.append(user_id, "assistant", final.strip())

    async def stream_chat_auto(
        self, user_id: str, message: str, context: str | None = None, model: str | None = None
    ) -> AsyncGenerator[str, None]:
        """Like stream_chat, but runs web_search automatically when the model requests it."""
        self.history.append(user_id, "user", message)

        now = datetime.now().strftime("%A, %d %B %Y, %H:%M")
        system = f"{SYSTEM_PROMPT}\n\nCurrent date and time: {now}"
        if context:
            system = f"{system}\n\n{context}"
        messages = [
            {"role": "system", "content": system},
            *self.history.get(user_id),
        ]

        # Grab last assistant message before appending user turn (used by the gate)
        _hist_so_far = self.history.get(user_id)
        _last_assistant = next(
            (m["content"] for m in reversed(_hist_so_far) if m["role"] == "assistant"), ""
        )

        _model = model or self.model

        # Fast gate: skip tool-check for messages with no search-relevant keywords
        if not _needs_search_check(message, _last_assistant):
            accumulated = ""
            async for chunk in await self._client.chat(
                model=_model,
                messages=messages,
                options={"stop": ["<|im_start|>", "<|im_end|>", "<|im_start|>system"]},
                stream=True,
            ):
                accumulated += chunk.message.content or ""
                clean = accumulated
                for tok in ("<|im_start|>system", "<|im_start|>", "<|im_end|>"):
                    clean = clean.split(tok)[0]
                yield clean
            final = accumulated
            for tok in ("<|im_start|>system", "<|im_start|>", "<|im_end|>"):
                final = final.split(tok)[0]
            self.history.append(user_id, "assistant", final.strip())
            return

        # Non-streaming pass to check whether the model wants to search
        tool_resp = await self._client.chat(
            model=_model,
            messages=messages,
            tools=[_SEARCH_TOOL],
            options={"stop": ["<|im_start|>", "<|im_end|>", "<|im_start|>system"]},
        )

        if tool_resp.message.tool_calls:
            query = tool_resp.message.tool_calls[0].function.arguments.get("query", message)

            yield f'🔍 *Searching for "{query}"...*'

            loop = asyncio.get_running_loop()
            search_result = await loop.run_in_executor(None, web_search, query)

            messages_with_tool = messages + [
                tool_resp.message,
                {"role": "tool", "content": search_result, "name": "web_search"},
            ]

            accumulated = ""
            async for chunk in await self._client.chat(
                model=_model,
                messages=messages_with_tool,
                options={"stop": ["<|im_start|>", "<|im_end|>", "<|im_start|>system"]},
                stream=True,
            ):
                accumulated += chunk.message.content or ""
                clean = accumulated
                for tok in ("<|im_start|>system", "<|im_start|>", "<|im_end|>"):
                    clean = clean.split(tok)[0]
                yield clean

            final = accumulated
            for tok in ("<|im_start|>system", "<|im_start|>", "<|im_end|>"):
                final = final.split(tok)[0]
            self.history.append(user_id, "assistant", final.strip())
        else:
            # No tool call — the tool-check pass already produced the full reply
            reply = tool_resp.message.content or ""
            for tok in ("<|im_start|>system", "<|im_start|>", "<|im_end|>"):
                reply = reply.replace(tok, "")
            reply = reply.strip()
            self.history.append(user_id, "assistant", reply)
            yield reply

    async def list_models(self) -> list[str]:
        result = await self._client.list()
        return [m.model for m in result.models]

    def clear_history(self, user_id: str) -> None:
        self.history.clear(user_id)

    def history_count(self, user_id: str) -> int:
        return self.history.count(user_id)
