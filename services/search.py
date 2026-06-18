import os
import httpx

_SERPER_URL = "https://google.serper.dev/search"


def web_search(query: str, max_results: int = 6) -> str:
    api_key = os.environ["SERPER_API_KEY"]

    resp = httpx.post(
        _SERPER_URL,
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        json={"q": query, "num": max_results},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    results = data.get("organic", [])
    if not results:
        return f'No results found for "{query}". Answer based on what you know.'

    lines = [
        f'Use the following search results to answer the query "{query}".',
        "Answer naturally and directly — do NOT mention search results, links, or tell the user to check anything.",
    ]
    for i, r in enumerate(results, 1):
        title = r.get("title", "").strip()
        snippet = r.get("snippet", "").strip()
        lines.append(f"{i}. {title}: {snippet}")

    return "\n\n".join(lines)
