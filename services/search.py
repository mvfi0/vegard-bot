import os
import httpx

_TAVILY_URL = "https://api.tavily.com/search"


def web_search(query: str, max_results: int = 6) -> str:
    api_key = os.environ["TAVILY_API_KEY"]

    resp = httpx.post(
        _TAVILY_URL,
        json={"api_key": api_key, "query": query, "max_results": max_results},
        timeout=10,
    )
    resp.raise_for_status()

    results = resp.json().get("results", [])
    if not results:
        return f'No results found for "{query}". Answer based on what you know.'

    lines = [
        f'Use the following search results to answer the query "{query}".',
        "Answer naturally and directly — do NOT mention search results, links, or tell the user to check anything.",
    ]
    for i, r in enumerate(results, 1):
        title = r.get("title", "").strip()
        content = r.get("content", "").strip()
        lines.append(f"{i}. {title}: {content}")

    return "\n\n".join(lines)
