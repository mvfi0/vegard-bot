import ollama
from .history import HistoryManager

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

You run on his machine. What's said here stays here.\
"""


class OllamaService:
    def __init__(self, model: str):
        self.model = model
        self._client = ollama.AsyncClient()
        self.history = HistoryManager()

    async def chat(self, user_id: str, message: str) -> str:
        self.history.append(user_id, "user", message)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *self.history.get(user_id),
        ]

        response = await self._client.chat(model=self.model, messages=messages)
        reply: str = response.message.content

        self.history.append(user_id, "assistant", reply)
        return reply

    async def list_models(self) -> list[str]:
        result = await self._client.list()
        return [m.model for m in result.models]

    def clear_history(self, user_id: str) -> None:
        self.history.clear(user_id)

    def history_count(self, user_id: str) -> int:
        return self.history.count(user_id)
