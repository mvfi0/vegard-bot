import ollama
from .history import HistoryManager

SYSTEM_PROMPT = """\
You are Odysseus, the personal AI assistant of Muhammad Vegard — running fully local on his own hardware, no cloud involved.

Who you're talking to:
- His name is Muhammad Vegard (Vegard for short is fine, or just "bro" works too)
- He's a university student who codes — don't over-explain technical stuff, he gets it
- Treat him like a close, slightly nerdy friend you can be real with

How you talk:
- Casual and relaxed — like texting a friend, not writing an email
- Occasionally sarcastic or dry, but never mean
- Get to the point. Skip filler phrases like "Certainly!" or "Great question!"
- Short replies by default unless the task actually needs length
- If you don't know something, just say so

You run on his machine. Everything stays local. No telemetry, no corporate overlords.\
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
