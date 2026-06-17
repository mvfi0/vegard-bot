import httpx


class OdysseusClient:
    def __init__(self, base_url: str):
        self._base = base_url.rstrip("/")
        # Generous timeout — local LLMs can take a while to generate
        self._http = httpx.AsyncClient(timeout=120.0)

    async def chat(self, user_id: int, message: str, context: str | None = None) -> str:
        payload: dict = {"user_id": str(user_id), "message": message}
        if context:
            payload["context"] = context
        resp = await self._http.post(f"{self._base}/chat", json=payload)
        resp.raise_for_status()
        return resp.json()["reply"]

    async def clear(self, user_id: int) -> None:
        await self._http.delete(f"{self._base}/chat/{user_id}")

    async def history_count(self, user_id: int) -> int:
        resp = await self._http.get(f"{self._base}/chat/{user_id}/history")
        resp.raise_for_status()
        return resp.json()["message_count"]

    async def aclose(self) -> None:
        await self._http.aclose()
