import os
import re
import httpx


def fetch_lyrics(artist: str, title: str) -> str | None:
    """Fetch lyrics from lyrics.ovh. Returns the lyrics string or None if not found."""
    try:
        resp = httpx.get(
            f"https://api.lyrics.ovh/v1/{artist}/{title}",
            timeout=10,
            follow_redirects=True,
        )
        if resp.status_code == 200:
            return resp.json().get("lyrics")
    except Exception:
        pass
    return None


_FOOTER_RE = re.compile(
    r"(you might also like|see \w+ lyrics|more on genius|^embed$"
    r"|writers?:|lyrics powered by|all rights reserved|\d+ contributors)",
    re.IGNORECASE,
)


def fetch_lyrics_web(query: str) -> str | None:
    """
    Search Tavily for the top lyrics page and return its raw text content.
    No LLM — raw page text stripped of footer noise.
    """
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return None
    try:
        resp = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": f"{query} lyrics",
                "max_results": 3,
                "include_raw_content": True,
                "search_depth": "basic",
            },
            timeout=20,
        )
        resp.raise_for_status()
        for result in resp.json().get("results", []):
            raw = result.get("raw_content") or result.get("content", "")
            if not raw or len(raw) < 200:
                continue
            return _clean_raw(raw)
    except Exception:
        pass
    return None


def _clean_raw(raw: str) -> str:
    """Strip page boilerplate from a raw lyrics page, keeping only the lyric lines."""
    lines = []
    for line in raw.splitlines():
        if _FOOTER_RE.search(line):
            break
        lines.append(line)
    return "\n".join(lines).strip()


# Suffixes commonly appended to YouTube titles that aren't part of the song name
_YT_NOISE = re.compile(
    r"[\(\[【][^)\]】]*"
    r"(official|lyrics?|video|audio|cover|mv|pv|カバー|歌ってみた|full|hd|4k|ver\.?)"
    r"[^)\]】]*[\)\]】]",
    re.IGNORECASE,
)


def parse_yt_title(yt_title: str) -> tuple[str, str] | None:
    """
    Try to split a YouTube title into (artist, song).
    Handles: "Artist - Song", "Song by Artist", "Channel | Song by Artist"
    """
    cleaned = _YT_NOISE.sub("", yt_title).strip(" -–|")

    for sep in (" - ", " – "):
        if sep in cleaned:
            left, right = cleaned.split(sep, 1)
            return left.strip(), right.strip()

    candidate = cleaned
    if " | " in cleaned:
        candidate = cleaned.split(" | ")[-1].strip()

    lower = candidate.lower()
    if " by " in lower:
        idx = lower.index(" by ")
        song = candidate[:idx].strip()
        artist = candidate[idx + 4:].strip()
        return artist, song

    return None
