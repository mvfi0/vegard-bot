import json
from collections import defaultdict, deque
from pathlib import Path

MAX_HISTORY = 20  # total messages (user + assistant) per channel


class HistoryManager:
    def __init__(self, persist_path: Path | None = None):
        self._path = persist_path
        self._store: dict[str, deque] = defaultdict(lambda: deque(maxlen=MAX_HISTORY))
        if self._path and self._path.exists():
            self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            for channel_id, messages in data.items():
                d: deque = deque(maxlen=MAX_HISTORY)
                d.extend(messages[-MAX_HISTORY:])
                self._store[channel_id] = d
        except Exception:
            pass  # corrupt or missing — start fresh

    def _save(self) -> None:
        if not self._path:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {k: list(v) for k, v in self._store.items()}
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def append(self, user_id: str, role: str, content: str) -> None:
        self._store[user_id].append({"role": role, "content": content})
        self._save()

    def get(self, user_id: str) -> list[dict]:
        return list(self._store[user_id])

    def clear(self, user_id: str) -> None:
        self._store.pop(user_id, None)
        self._save()

    def count(self, user_id: str) -> int:
        return len(self._store[user_id])

    def pop_last(self, user_id: str, n: int = 2) -> None:
        store = self._store[user_id]
        for _ in range(min(n, len(store))):
            store.pop()
        self._save()
