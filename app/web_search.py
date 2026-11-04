"""Bounded Tavily search. Source material stays request-local."""

import asyncio
import ipaddress
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.agents.budget import BudgetExceeded, current_budget
from app.providers import ProviderError


def safe_url(value):
    if not isinstance(value, str) or len(value) > 2048 or re.search(r"[\s\\\x00-\x1f]", value):
        return None
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
            return None
        if host.lower() == "localhost" or host.lower().endswith((".local", ".localhost")):
            return None
        try:
            if not ipaddress.ip_address(host).is_global:
                return None
        except ValueError:
            if "." not in host:
                return None
        port = parsed.port
        netloc = host.lower() + (f":{port}" if port and port not in {80, 443} else "")
        return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))
    except ValueError:
        return None


class TavilySearch:
    def __init__(self, key, client, domains=()):
        self.key, self.client, self.domains = key, client, list(domains)

    @property
    def available(self):
        return bool(self.key)

    async def search(self, query):
        budget = current_budget.get()
        if budget is None:
            raise RuntimeError("Web search requires a request budget")
        budget.consume_web()
        try:
            async with self.client.stream(
                "POST",
                "https://api.tavily.com/search",
                headers={"Authorization": f"Bearer {self.key}"},
                json={
                    "query": query,
                    "search_depth": "basic",
                    "include_answer": False,
                    "auto_parameters": False,
                    "max_results": 3,
                    "include_raw_content": False,
                    "include_domains": self.domains,
                },
                timeout=12,
            ) as response:
                if response.status_code != 200:
                    raise ProviderError(
                        "Web search unavailable.",
                        retryable=response.status_code in {408, 429, 500, 502, 503, 504},
                    )
                raw = bytearray()
                async for part in response.aiter_bytes():
                    raw.extend(part)
                    if len(raw) > 128000:
                        raise ProviderError("Web search response exceeded its limit.")
            payload = json.loads(raw)
            if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                raise ValueError()
            hits, seen = [], set()
            for row in payload["results"][:3]:
                if not isinstance(row, dict):
                    continue
                url = safe_url(row.get("url"))
                content = row.get("content")
                if not url or url in seen or not isinstance(content, str) or not content.strip():
                    continue
                seen.add(url)
                hits.append(
                    {
                        "source_type": "web",
                        "url": url,
                        "title": str(row.get("title") or "Web source")[:200],
                        "text": content[:2000],
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        "published_date": str(row.get("published_date") or "")[:40],
                    }
                )
            return hits
        except (httpx.TimeoutException, httpx.NetworkError):
            raise ProviderError("Web search unavailable.", retryable=True) from None
        except (ValueError, httpx.HTTPError):
            raise ProviderError("Web search returned invalid data.") from None


async def bounded_search(client, query):
    """At most one retry, sharing the same two-attempt budget across all queries."""
    for attempt in range(2):
        try:
            return await client.search(query)
        except ProviderError as exc:
            budget = current_budget.get()
            if not exc.retryable or attempt or budget.web_calls >= 2:
                raise
            await asyncio.sleep(0.1)
    raise BudgetExceeded()
