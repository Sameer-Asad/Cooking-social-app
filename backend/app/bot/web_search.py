"""
Web search tool for the bot's agentic loop (Sec 4.1's "web search + 2-3
other tools"). Provider is config-driven (Sec 3.1's pattern for
WHISPER_MODEL/GROQ_MODEL — swap via .env, not code).

Default provider: DuckDuckGo's free, keyless Instant Answer API
(https://api.duckduckgo.com/). Important honest limitation: this is an
*instant-answer* API, not a general web search index — it returns a
Wikipedia-style abstract and/or a short list of related topics when DDG
has one for the query, and returns nothing for the majority of specific,
long-tail queries (which, for a recipe bot, is a lot of them). It's wired
up here because it's real, free, and needs no API key to test — not
because it's a complete solution. Swapping WEB_SEARCH_PROVIDER to a real
search-index provider (Tavily, Serper, Bing) is the natural next step;
add a new branch in `search_web` when that provider's real request/
response shape has been verified against its own docs, following the
same pattern as this one.
"""

from __future__ import annotations

import httpx
from langsmith import traceable

from app.config import settings

_DDG_ENDPOINT = "https://api.duckduckgo.com/"
_MAX_RESULT_CHARS = (
    1200  # keep tool output bounded — this feeds an LLM context, not a user-facing page
)


async def _search_duckduckgo(query: str) -> str:
    params = {
        "q": query,
        "format": "json",
        "no_html": "1",
        "skip_disambig": "1",
        "no_redirect": "1",
    }
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.get(_DDG_ENDPOINT, params=params)
        response.raise_for_status()
        data = response.json()

    parts: list[str] = []

    abstract = data.get("AbstractText")
    if abstract:
        heading = data.get("Heading") or query
        source_url = data.get("AbstractURL") or ""
        parts.append(
            f"{heading}: {abstract}" + (f" ({source_url})" if source_url else "")
        )

    for topic in data.get("RelatedTopics", [])[:3]:
        # RelatedTopics can be either a flat {Text, FirstURL} entry or a
        # nested {"Topics": [...]} group — handle both per the API's
        # actual (somewhat inconsistent) documented shape.
        if "Text" in topic and "FirstURL" in topic:
            parts.append(topic["Text"])
        elif "Topics" in topic:
            for sub in topic["Topics"][:2]:
                if "Text" in sub:
                    parts.append(sub["Text"])

    if not parts:
        return f"No instant-answer result found for {query!r}. This provider only covers well-known topics — treat this as inconclusive, not as evidence the information doesn't exist."

    joined = " | ".join(parts)
    return joined[:_MAX_RESULT_CHARS]


@traceable(name="web_search_tool")
async def search_web(query: str) -> str:
    if settings.web_search_provider == "duckduckgo":
        try:
            return await _search_duckduckgo(query)
        except httpx.HTTPError as exc:
            return f"[web_search temporarily unavailable: {exc}]"
    return f"[unknown WEB_SEARCH_PROVIDER={settings.web_search_provider!r} — no branch implemented for it yet]"
