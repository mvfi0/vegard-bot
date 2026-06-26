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
    r"|lyrics powered by|all rights reserved|\d+ contributors?"
    r"|^credits$|^tags$|^comments$|sign up and drop|genius is the ultimate"
    r"|^song bio$|^about$|^q&a$|^translations?$"
    r"|^song overview$|review and highlights|^quick summary$"
    r"|how to format lyrics|transcription guide|transcribers.{0,10}forum"
    r"|frequently asked questions about the song)",
    re.IGNORECASE,
)

# Genius placeholder text that means the lyrics haven't been added yet
_GENIUS_EMPTY_RE = re.compile(
    r"how to format lyrics|transcription guide", re.IGNORECASE
)

# Lines that are clearly page metadata, not lyrics
_META_LINE_RE = re.compile(
    r"^\d[\d,\.]*[KM]?\s*(view|viewer)|"       # "133.5K views", "1 viewer"
    r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d+,\s+\d{4}$|"
    r"^\d+\s*(contributor|translation)|"
    r"^(Producer|Featuring|Written|Album|Release|Track\s+\d|Label)\b|"
    r"^\d+$|"                                   # lone numbers ("3")
    r"^[•·\-\*]\s*[A-Z#]?\s*$|"               # bullet nav items (• A, • B, - #)
    r"^[A-Z#]$|"                               # single-letter alphabet navigation
    r"^#{1,6}\s+",                             # markdown headers (#### Quick summary)
    re.IGNORECASE,
)

# Only match real lyrics section headers — not arbitrary [brackets] in metadata
_SECTION_START_RE = re.compile(
    r'^\[(Verse|Chorus|Pre.?Chorus|Bridge|Outro|Intro|Hook|Refrain|Interlude)\b',
    re.IGNORECASE | re.MULTILINE,
)

# [[Section]](/url) → [Section]  (Genius section header links)
_MD_SECTION_RE = re.compile(r'\[\[([^\]]+)\]\]\([^)]+\)')
# [text](url) — applied with DOTALL so it catches multi-line link text
_MD_LINK_RE = re.compile(r'\[([^\]]*)\]\([^)]+\)', re.DOTALL)


def fetch_lyrics_web(query: str) -> str | None:
    """
    Search Tavily for the top lyrics page and return its raw text content.
    Skips English-translation pages; prefers romanized/original.
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
                "max_results": 5,
                "include_raw_content": True,
                "search_depth": "basic",
            },
            timeout=20,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])

        # Prefer non-translation results — skip pages explicitly marked as translations
        def _is_translation(r: dict) -> bool:
            url = r.get("url", "").lower()
            title = r.get("title", "").lower()
            return "english-translation" in url or "english translation" in title

        ordered = [r for r in results if not _is_translation(r)] + \
                  [r for r in results if _is_translation(r)]

        # Prefer results whose raw content has proper [Verse]/[Chorus] section markers
        def _has_sections(r: dict) -> bool:
            return bool(_SECTION_START_RE.search(r.get("raw_content") or ""))

        ordered.sort(key=lambda r: (not _has_sections(r), not _is_translation(r)))

        for result in ordered:
            raw = result.get("raw_content") or result.get("content", "")
            if not raw or len(raw) < 200:
                continue
            # Skip Genius placeholder pages (lyrics not yet transcribed)
            if _GENIUS_EMPTY_RE.search(raw):
                continue
            cleaned = _clean_raw(raw)
            if cleaned and len(cleaned) > 100:
                return cleaned
    except Exception:
        pass
    return None


def _clean_raw(raw: str) -> str:
    """Strip page boilerplate from a raw lyrics page, keeping only the lyric lines."""
    # Strip links on the full text first so multi-line Genius links are handled
    text = _MD_SECTION_RE.sub(r'[\1]', raw)                    # [[Chorus]](/url) → [Chorus]
    text = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', text)           # ![alt](url) images
    text = re.sub(r'^!.+$', '', text, flags=re.MULTILINE)      # !standalone image lines
    text = _MD_LINK_RE.sub(r'\1', text)                        # [line1\nline2](url) → line1\nline2

    lines = []
    for line in text.splitlines():
        if _FOOTER_RE.search(line.strip()):
            break
        if _META_LINE_RE.match(line.strip()):
            continue
        lines.append(line)

    content = "\n".join(lines)

    # Slice to the first real lyrics section header ([Verse], [Chorus], etc.)
    # Using a strict allowlist avoids matching stray [brackets] in page metadata
    section_match = _SECTION_START_RE.search(content)
    if section_match:
        content = content[section_match.start():]

    # Cut at "Song Bio" / biography prose that follows the lyrics
    bio_match = re.search(r'^song bio\b', content, re.IGNORECASE | re.MULTILINE)
    if bio_match:
        content = content[:bio_match.start()]

    return content.strip()


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
