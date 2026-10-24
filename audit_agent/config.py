from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path | None = None) -> None:
    env_path = path or ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    model_agent: str
    model_judge: str
    price_in_cny_per_m: float
    price_out_cny_per_m: float
    timeout_s: float = 90.0
    # auto: enforce budget assertions only when the estimate is calibrated
    # against the provider's balance delta. always / never override it.
    cost_enforce: str = "auto"


def get_settings() -> Settings:
    load_env()
    api_key = os.environ.get("LLM_API_KEY", "")
    if not api_key:
        raise RuntimeError("LLM_API_KEY is missing. Add it to .env")
    return Settings(
        api_key=api_key,
        base_url=os.environ.get("LLM_BASE_URL", "https://api.deepseek.com"),
        model_agent=os.environ.get("LLM_MODEL", "deepseek-flash"),
        model_judge=os.environ.get("LLM_JUDGE_MODEL", "deepseek-v4-pro"),
        price_in_cny_per_m=float(os.environ.get("PRICE_IN_CNY_PER_M", "2.0")),
        price_out_cny_per_m=float(os.environ.get("PRICE_OUT_CNY_PER_M", "8.0")),
        cost_enforce=os.environ.get("COST_ENFORCE", "auto").strip().lower(),
    )


def get_client(settings: Settings | None = None) -> OpenAI:
    s = settings or get_settings()
    return OpenAI(
        api_key=s.api_key,
        base_url=s.base_url,
        timeout=s.timeout_s,
        max_retries=2,
    )