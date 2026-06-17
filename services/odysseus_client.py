import json
from pathlib import Path

import httpx

_SESSIONS_FILE = Path(__file__).parent.parent / "odysseus_sessions.json"
_CHATML_STOP = ("<|im_start|>", "<|im_end|>", "<|eot_id|>", "<|end_of_text|>")


def _strip_chatml(text: str) -> str:
    for tok in _CHATML_STOP:
        text = text.split(tok)[0]
    return text.strip()


def _load_sessions() -> dict:
    if _SESSIONS_FILE.exists():
        return json.loads(_SESSIONS_FILE.read_text(encoding="utf-8"))
    return {}


def _save_sessions(sessions: dict) -> None:
    _SESSIONS_FILE.write_text(json.dumps(sessions, indent=2), encoding="utf-8")


class OdysseusClient:
    def __init__(self, base_url: str, api_key: str, model: str = "vegard:latest"):
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._http = httpx.AsyncClient(timeout=180.0)
        self._sessions: dict = _load_sessions()
        self._model = model

    async def chat(self, channel_id: str, message: str, context: str | None = None) -> str:
        full_message = f"{context}\n\n{message}" if context else message
        session_id = self._sessions.get(channel_id)

        # Pass model explicitly so Odysseus skips "auto" discovery and uses
        # whichever Ollama model is already loaded, avoiding a slow model swap.
        payload: dict = {"message": full_message, "model": self._model}
        if session_id:
            payload["session"] = session_id

        resp = await self._http.post(
            f"{self._base}/api/v1/chat",
            json=payload,
            headers=self._headers,
        )
        resp.raise_for_status()
        data = resp.json()

        returned_sid = data.get("session_id")
        if returned_sid and returned_sid != session_id:
            self._sessions[channel_id] = returned_sid
            _save_sessions(self._sessions)

        return _strip_chatml(data["response"])

    def clear_session(self, channel_id: str) -> None:
        if channel_id in self._sessions:
            self._sessions.pop(channel_id)
            _save_sessions(self._sessions)

    async def clear(self, channel_id: str) -> None:
        if channel_id in self._sessions:
            self._sessions.pop(channel_id)
            _save_sessions(self._sessions)

    async def history_count(self, channel_id: str) -> int:
        session_id = self._sessions.get(channel_id)
        if not session_id:
            return 0
        resp = await self._http.get(
            f"{self._base}/api/history/{session_id}",
            headers=self._headers,
        )
        resp.raise_for_status()
        history = resp.json()
        return len(history) if isinstance(history, list) else 0

    async def aclose(self) -> None:
        await self._http.aclose()
