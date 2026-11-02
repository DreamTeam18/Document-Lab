import json
import math

import httpx

from app.config import Settings


class ProviderError(Exception):
    """Public-safe upstream failure; never includes keys, URLs, or response bodies."""


def vector_literal(values: list[float], dimensions: int = 768) -> str:
    if len(values) != dimensions or not all(math.isfinite(x) for x in values):
        raise ProviderError("Embedding provider returned an invalid vector")
    return "[" + ",".join(str(float(x)) for x in values) + "]"


class Providers:
    def __init__(self, config: Settings, client: httpx.AsyncClient):
        self.config = config
        self.client = client

    async def _post(self, url, **kwargs):
        try:
            response = await self.client.post(url, **kwargs)
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict):
                raise ProviderError("Model provider returned an invalid response")
            if "error" in body:
                raise ProviderError("Model provider rejected the request")
            return body
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError("Model provider unavailable or rate-limited") from exc

    async def chat(self, system: str, prompt: str, max_tokens: int = 1200) -> str:
        if not self.config.openrouter_api_key.get_secret_value():
            raise ProviderError("OPENROUTER_API_KEY is not configured")
        body = await self._post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": "Bearer " + self.config.openrouter_api_key.get_secret_value()
            },
            json={
                "model": self.config.openrouter_model,
                "temperature": 0,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            },
        )
        try:
            result = body["choices"][0]["message"]["content"]
            if not isinstance(result, str) or not result.strip():
                raise ValueError("Empty response")
            return result.strip()
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError("Model provider returned no usable answer") from exc

    async def stream_chat(self, system: str, prompt: str, max_tokens: int = 1200):
        """Yield real content deltas; never expose reasoning or upstream error bodies."""
        if not self.config.openrouter_api_key.get_secret_value():
            raise ProviderError("OPENROUTER_API_KEY is not configured")
        seen = False
        try:
            async with self.client.stream(
                "POST",
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": "Bearer " + self.config.openrouter_api_key.get_secret_value()
                },
                json={
                    "model": self.config.openrouter_model,
                    "temperature": 0,
                    "max_tokens": max_tokens,
                    "stream": True,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if raw == "[DONE]":
                        if not seen:
                            raise ProviderError("Model provider returned no usable answer")
                        return
                    if not raw:
                        continue
                    body = json.loads(raw)
                    if "error" in body:
                        raise ProviderError("Model provider interrupted the answer stream")
                    for choice in body.get("choices", []):
                        if choice.get("finish_reason") in ("error", "length", "content_filter"):
                            raise ProviderError("Model provider did not complete the answer")
                        delta = choice.get("delta", {}).get("content")
                        if isinstance(delta, str) and delta:
                            seen = True
                            yield delta
                raise ProviderError("Model provider stream ended before completion")
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            raise ProviderError("Model provider stream unavailable or invalid") from None

    async def embed(self, text: str) -> list[float]:
        config = self.config
        if not config.openrouter_api_key.get_secret_value():
            raise ProviderError("OPENROUTER_API_KEY is not configured")
        body = await self._post(
            "https://openrouter.ai/api/v1/embeddings",
            headers={"Authorization": "Bearer " + config.openrouter_api_key.get_secret_value()},
            json={
                "model": config.embedding_model,
                "input": text,
                "dimensions": config.embedding_dimensions,
            },
        )
        try:
            data = body.get("data")
            if not isinstance(data, list) or not data or not isinstance(data[0], dict):
                raise ValueError("Invalid embedding envelope")
            values = data[0].get("embedding")
            if not isinstance(values, list):
                raise ValueError("Invalid embedding values")
            values = [float(value) for value in values]
            vector_literal(values, config.embedding_dimensions)
            norm = math.sqrt(sum(x * x for x in values))
            if norm == 0 or not math.isfinite(norm):
                raise ValueError("Invalid embedding norm")
            return [x / norm for x in values]
        except (TypeError, ValueError) as exc:
            raise ProviderError("Embedding provider returned an invalid vector") from exc
