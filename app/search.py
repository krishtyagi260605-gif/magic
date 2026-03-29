from __future__ import annotations

import json
import re
from html import unescape
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


def _fetch_json(url: str) -> dict[str, object]:
    request = Request(url, headers={"User-Agent": "Magic/0.7"})
    with urlopen(request, timeout=4.0) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("unexpected JSON payload")
        return payload


def _clean_html(text: str) -> str:
    stripped = re.sub(r"<[^>]+>", "", text or "")
    return " ".join(unescape(stripped).split())


def _extract_direct_fact(query: str, snippets: list[str]) -> str | None:
    normalized = query.lower()
    haystack = " ".join(snippets)
    if "capital of" in normalized:
        match = re.search(r"capital of [^.]*?\b(?:has been|is)\s+([A-Z][A-Za-z-]*(?:\s+[A-Z][A-Za-z-]*){0,3})\b", haystack)
        if match:
            subject = normalized.split("capital of", 1)[1].strip().rstrip("?")
            answer = match.group(1).strip()
            if subject:
                return f"{answer} is the capital of {subject.title()}."
    return None


def _normalize_query(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^(search|look up|lookup|google)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(what is|who is|when is|where is|how to|tell me about)\s+", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" ?") or text.strip()


def search_web(query: str) -> tuple[str, list[str]]:
    text = _normalize_query((query or "").strip())
    if not text:
        return "No search query provided.", []

    lower = text.lower()

    sources: list[str] = []
    answer_lines: list[str] = []

    ddg_url = "https://api.duckduckgo.com/?" + urlencode(
        {
            "q": text,
            "format": "json",
            "no_html": "1",
            "no_redirect": "1",
            "skip_disambig": "1",
        }
    )

    try:
        payload = _fetch_json(ddg_url)
        abstract = str(payload.get("AbstractText", "")).strip()
        heading = str(payload.get("Heading", "")).strip()
        answer = str(payload.get("Answer", "")).strip()
        definition = str(payload.get("Definition", "")).strip()
        abstract_url = str(payload.get("AbstractURL", "")).strip()

        if heading:
            answer_lines.append(heading)
        if answer:
            answer_lines.append(answer)
        if abstract:
            answer_lines.append(abstract)
        elif definition:
            answer_lines.append(definition)
        if abstract_url:
            sources.append(abstract_url)

        related = payload.get("RelatedTopics", [])
        if isinstance(related, list):
            bullet_lines: list[str] = []
            for item in related[:4]:
                if isinstance(item, dict):
                    if "Text" in item and item.get("FirstURL"):
                        bullet_lines.append(f"- {item['Text']}")
                        sources.append(str(item["FirstURL"]))
                    elif isinstance(item.get("Topics"), list):
                        for topic in item["Topics"][:2]:
                            if isinstance(topic, dict) and topic.get("Text") and topic.get("FirstURL"):
                                bullet_lines.append(f"- {topic['Text']}")
                                sources.append(str(topic["FirstURL"]))
                if len(bullet_lines) >= 4:
                    break
            if bullet_lines:
                answer_lines.append("Related:")
                answer_lines.extend(bullet_lines[:4])
    except Exception:
        pass

    if answer_lines:
        unique_sources = list(dict.fromkeys(sources))
        return "\n".join(answer_lines).strip(), unique_sources[:5]

    wiki_search_url = (
        "https://en.wikipedia.org/w/api.php?"
        + urlencode(
            {
                "action": "query",
                "list": "search",
                "srsearch": text,
                "format": "json",
                "utf8": "1",
                "srlimit": "3",
            }
        )
    )

    try:
        search_payload = _fetch_json(wiki_search_url)
        query_payload = search_payload.get("query", {})
        search_items = query_payload.get("search", []) if isinstance(query_payload, dict) else []
        if isinstance(search_items, list) and search_items:
            snippets: list[str] = []
            for item in search_items[:3]:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title", "")).strip()
                snippet = _clean_html(str(item.get("snippet", ""))).strip()
                if title:
                    page_url = f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"
                    sources.append(page_url)
                    if snippet:
                        snippets.append(f"- {title}: {snippet}")
                    else:
                        snippets.append(f"- {title}")
            direct_fact = _extract_direct_fact(text, snippets)
            if direct_fact:
                return (direct_fact, list(dict.fromkeys(sources))[:5])
            if snippets:
                return (
                    "Search results:\n" + "\n".join(snippets),
                    list(dict.fromkeys(sources))[:5],
                )
    except Exception:
        pass

    return (
        "I could not find a strong live web result for that query right now. Try rephrasing it more specifically.",
        [],
    )
