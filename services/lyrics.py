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
    Returns None if no reliable split is found.
    Handles: "Artist - Song", "Song by Artist", "Channel | Song by Artist"
    """
    cleaned = _YT_NOISE.sub("", yt_title).strip(" -–|")

    # "Artist - Song" or "Artist – Song"
    for sep in (" - ", " – "):
        if sep in cleaned:
            left, right = cleaned.split(sep, 1)
            return left.strip(), right.strip()

    # "... | Song by Artist" — pipe narrows to the song segment
    candidate = cleaned
    if " | " in cleaned:
        candidate = cleaned.split(" | ")[-1].strip()

    # "Song by Artist"
    lower = candidate.lower()
    if " by " in lower:
        idx = lower.index(" by ")
        song = candidate[:idx].strip()
        artist = candidate[idx + 4:].strip()
        return artist, song

    return None
