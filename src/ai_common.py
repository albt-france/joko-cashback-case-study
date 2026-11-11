"""Shared helpers for the AI layer (review themes, "Ask the data", evaluation).

- The API key is read from .env (ANTHROPIC_API_KEY); nothing works without it, and every AI script
  has a documented fallback that runs without a key.
- Model: a recent, low-cost model (Claude Haiku 5.5). Override with AI_MODEL in .env.
- Determinism: current Claude models no longer accept a `temperature` parameter, so outputs are
  constrained instead with a fixed prompt, low effort and a strict JSON schema (structured outputs).
- Every call is logged (model, tokens, latency, cost) in logs/ai_calls.jsonl. No personal data is
  sent or logged: reviews have no author fields, and "Ask the data" runs on simulated data.
"""
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "logs" / "ai_calls.jsonl"

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

MODEL = os.getenv("AI_MODEL", "claude-haiku-5-5")
# USD per million tokens (Claude Haiku 5.5, prompts up to 100K tokens), checked 2026-11-11
PRICE_IN, PRICE_OUT = 0.10, 0.50


def has_key():
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def call_json(system, user, schema, max_tokens=2000, task="generic"):
    """One Claude call that must return JSON matching `schema`. Returns (dict, meta)."""
    import anthropic
    client = anthropic.Anthropic()
    t0 = time.time()
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
    )
    latency = time.time() - t0
    if response.stop_reason == "refusal":
        raise RuntimeError("model refused the request")
    text = next(b.text for b in response.content if b.type == "text")
    usage = response.usage
    cost = usage.input_tokens / 1e6 * PRICE_IN + usage.output_tokens / 1e6 * PRICE_OUT
    meta = {"task": task, "model": MODEL, "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens, "latency_s": round(latency, 2),
            "cost_usd": round(cost, 6), "stop_reason": response.stop_reason}
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **meta}) + "\n")
    return json.loads(text), meta
