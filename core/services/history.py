from collections import defaultdict, deque

MAX_HISTORY = 20  # total messages (user + assistant) per user


class HistoryManager:
    def __init__(self):
        self._store: dict[str, deque] = defaultdict(lambda: deque(maxlen=MAX_HISTORY))

    def append(self, user_id: str, role: str, content: str) -> None:
        self._store[user_id].append({"role": role, "content": content})

    def get(self, user_id: str) -> list[dict]:
        return list(self._store[user_id])

    def clear(self, user_id: str) -> None:
        self._store.pop(user_id, None)

    def count(self, user_id: str) -> int:
        return len(self._store[user_id])
