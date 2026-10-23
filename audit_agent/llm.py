from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
from openai import OpenAI

from .config import Settings


@dataclass
class LLMResult:
    response: Any
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int
    cost_cny: float


def chat(
    client: OpenAI,
    settings: Settings,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.0,
    max_tokens: int = 1200,
    model: str | None = None,
) -> LLMResult:
    start = time.perf_counter()
    kwargs: dict[str, Any] = {
        "model": model or settings.model_agent,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    response = client.chat.completions.create(**kwargs)
    latency_ms = int((time.perf_counter() - start) * 1000)
    usage = getattr(response, "usage", None)
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    cost = (
        prompt_tokens * settings.price_in_cny_per_m
        + completion_tokens * settings.price_out_cny_per_m
    ) / 1_000_000
    return LLMResult(
        response=response,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_cny=cost,
    )


def balance_cny(settings: Settings) -> float | None:
    try:
        response = httpx.get(
            f"{settings.base_url}/user/balance",
            headers={"Authorization": f"Bearer {settings.api_key}"},
            timeout=20,
        )
        response.raise_for_status()
        infos = response.json().get("balance_infos", [])
        for info in infos:
            if info.get("currency") == "CNY":
                return float(info.get("total_balance", 0))
    except Exception:
        return None
    return None
