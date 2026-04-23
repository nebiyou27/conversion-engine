"""LLM wrapper. OpenRouter dispatch + Langfuse tracing + per-run budget ceiling.

Every LLM call in this project goes through `complete()`. That is the contract.
Bypassing it means no cost tracking, no budget ceiling, no Langfuse trace —
the three things the memo's evidence graph depends on.

Design choices:
- OpenRouter via the OpenAI SDK (one key, many models, no extra dep).
- Pricing is a hardcoded table for the models we actually use. Unknown models
  are passed through with cost=0 and the caller takes responsibility.
- Budget is per-`run_id`. Caller constructs a `BudgetLedger`, threads it through.
- Langfuse failures are silent (operational concern; must not block agent work).
- LLM-call failures (network, auth, malformed) propagate; the caller handles them.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv
from openai import OpenAI

from integrations import langfuse_client as lf

load_dotenv()


# --- Models we actually use ---

MODELS: dict[str, str] = {
    "haiku":  "anthropic/claude-haiku-4.5",
    "sonnet": "anthropic/claude-sonnet-4.5",
}

# Per-million-token pricing on OpenRouter (USD). Source: openrouter.ai/models.
# Update when models or prices change. Unknown models cost 0 to the ledger.
PRICING: dict[str, tuple[float, float]] = {
    # model_id: (input_per_1M_usd, output_per_1M_usd)
    "anthropic/claude-haiku-4.5":  (0.25,  1.25),
    "anthropic/claude-sonnet-4.5": (3.00, 15.00),
    "openai/gpt-4o-mini":          (0.15,  0.60),
}

DEFAULT_BUDGET_USD = 0.50


# --- Errors and shapes ---

class BudgetExceededError(RuntimeError):
    """Raised before a call would push the ledger past its ceiling."""


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


# --- Budget ledger ---

class BudgetLedger:
    """Cumulative cost tracker per run.

    Check before calling: `ledger.check()` raises if already over ceiling.
    Record after calling: `ledger.add(cost_usd)`.

    The "check before, add after" order means the call that crosses the ceiling
    completes successfully — but the next call is blocked. That is intentional:
    failing mid-call is harder to reason about than failing at the next gate.
    """

    def __init__(self, *, run_id: str, ceiling_usd: float | None = None):
        if ceiling_usd is None:
            ceiling_usd = float(os.getenv("LLM_BUDGET_USD", str(DEFAULT_BUDGET_USD)))
        self.run_id = run_id
        self.ceiling_usd = ceiling_usd
        self.spent_usd = 0.0
        self.calls = 0

    def check(self) -> None:
        if self.spent_usd >= self.ceiling_usd:
            raise BudgetExceededError(
                f"run_id={self.run_id} spent_usd={self.spent_usd:.4f} "
                f">= ceiling_usd={self.ceiling_usd:.4f} ({self.calls} calls)"
            )

    def add(self, cost_usd: float) -> None:
        self.spent_usd += cost_usd
        self.calls += 1


# --- Client + cost helpers ---

_default_client: OpenAI | None = None


def _client() -> OpenAI:
    """Lazy-instantiate the OpenRouter-pointed OpenAI client.

    Lazy so the module is importable in test environments without OPENROUTER_API_KEY.
    """
    global _default_client
    if _default_client is None:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY not set — required for LLM calls. "
                "See .env.example."
            )
        _default_client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
    return _default_client


def _cost(model: str, input_tokens: int, output_tokens: int) -> float:
    if model not in PRICING:
        return 0.0
    in_per_m, out_per_m = PRICING[model]
    return (input_tokens * in_per_m + output_tokens * out_per_m) / 1_000_000


def _log_call(
    *,
    run_id: str,
    model: str,
    messages: list[dict],
    text: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    metadata: dict | None,
) -> None:
    """Best-effort Langfuse logging. Failures are swallowed.

    Tests monkeypatch this to a no-op so the suite has no network dependency.
    """
    try:
        t = lf.trace(name=run_id, metadata=metadata or {})
        t.generation(
            name=(metadata or {}).get("name", "complete"),
            model=model,
            input=messages,
            output=text,
            usage={
                "input": input_tokens,
                "output": output_tokens,
                "total": input_tokens + output_tokens,
                "unit": "TOKENS",
            },
            metadata={"cost_usd": cost_usd, "run_id": run_id},
        )
        lf.flush()
    except Exception:
        # Tracing is observability, not correctness. Never block the agent.
        pass


# --- Public API ---

def complete(
    messages: list[dict],
    *,
    run_id: str,
    ledger: BudgetLedger,
    model: str = MODELS["haiku"],
    max_tokens: int = 500,
    temperature: float = 0.0,
    client: OpenAI | None = None,
    metadata: dict | None = None,
) -> LLMResponse:
    """One LLM call with cost tracking + Langfuse logging.

    Raises BudgetExceededError BEFORE the call if the ledger is already over.
    """
    ledger.check()

    c = client or _client()
    response = c.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    text = (response.choices[0].message.content or "").strip()
    input_tokens = response.usage.prompt_tokens
    output_tokens = response.usage.completion_tokens
    cost = _cost(model, input_tokens, output_tokens)

    ledger.add(cost)
    _log_call(
        run_id=run_id,
        model=model,
        messages=messages,
        text=text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        metadata=metadata,
    )

    return LLMResponse(
        text=text,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
    )
