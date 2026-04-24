"""LLM wrapper contract tests.

Locks the budget contract (check before, add after), the cost calculation,
and the unknown-model passthrough. No real network calls — the OpenAI client
is faked, and Langfuse logging is monkey-patched to a no-op.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from integrations import llm
from integrations.llm import (
    DEFAULT_BUDGET_USD,
    MODELS,
    BudgetExceededError,
    BudgetLedger,
    LLMResponse,
    complete,
)


# --- Fake OpenAI client ---

@dataclass
class _FakeUsage:
    prompt_tokens: int
    completion_tokens: int


@dataclass
class _FakeMessage:
    content: str


@dataclass
class _FakeChoice:
    message: _FakeMessage


@dataclass
class _FakeResponse:
    choices: list[_FakeChoice]
    usage: _FakeUsage


class _FakeCompletions:
    def __init__(self, response: _FakeResponse):
        self._response = response
        self.last_kwargs: dict[str, Any] | None = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return self._response


class _FakeChat:
    def __init__(self, completions: _FakeCompletions):
        self.completions = completions


class FakeClient:
    def __init__(self, content: str = "ok", prompt_tokens: int = 100, completion_tokens: int = 50):
        usage = _FakeUsage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
        choice = _FakeChoice(message=_FakeMessage(content=content))
        response = _FakeResponse(choices=[choice], usage=usage)
        self._completions = _FakeCompletions(response)
        self.chat = _FakeChat(self._completions)

    @property
    def last_kwargs(self):
        return self._completions.last_kwargs


@pytest.fixture(autouse=True)
def _silence_langfuse(monkeypatch):
    """Replace Langfuse logging with a no-op so tests have zero network deps."""
    monkeypatch.setattr(llm, "_log_call", lambda **kwargs: None)


# --- Ledger ---

def test_ledger_starts_at_zero():
    ledger = BudgetLedger(run_id="r1", ceiling_usd=1.0)
    assert ledger.spent_usd == 0.0
    assert ledger.calls == 0
    assert ledger.ceiling_usd == 1.0


def test_ledger_default_ceiling_is_constant_when_env_unset(monkeypatch):
    monkeypatch.delenv("LLM_BUDGET_USD", raising=False)
    ledger = BudgetLedger(run_id="r1")
    assert ledger.ceiling_usd == DEFAULT_BUDGET_USD


def test_ledger_default_ceiling_reads_env_when_set(monkeypatch):
    monkeypatch.setenv("LLM_BUDGET_USD", "1.50")
    ledger = BudgetLedger(run_id="r1")
    assert ledger.ceiling_usd == 1.50


def test_ledger_check_raises_when_at_or_over_ceiling():
    ledger = BudgetLedger(run_id="r1", ceiling_usd=0.10)
    ledger.spent_usd = 0.10
    with pytest.raises(BudgetExceededError):
        ledger.check()


# --- complete() contract ---

def test_complete_blocks_call_when_budget_exhausted():
    ledger = BudgetLedger(run_id="r1", ceiling_usd=0.10)
    ledger.spent_usd = 0.15
    fake = FakeClient()

    with pytest.raises(BudgetExceededError):
        complete(
            [{"role": "user", "content": "hi"}],
            run_id="r1", ledger=ledger, client=fake,
        )

    # The call must NOT have been dispatched to the LLM.
    assert fake.last_kwargs is None


def test_complete_records_cost_to_ledger():
    ledger = BudgetLedger(run_id="r1", ceiling_usd=10.0)
    fake = FakeClient(content="response", prompt_tokens=1000, completion_tokens=500)

    resp = complete(
        [{"role": "user", "content": "hi"}],
        model="anthropic/claude-haiku-4.5",
        run_id="r1", ledger=ledger, client=fake,
    )

    # haiku: (1000*0.25 + 500*1.25) / 1_000_000 = (250 + 625) / 1e6 = $0.000875
    assert resp.cost_usd == pytest.approx(0.000875)
    assert ledger.spent_usd == pytest.approx(0.000875)
    assert ledger.calls == 1
    assert ledger.per_call_log[0]["model"] == "anthropic/claude-haiku-4.5"


def test_complete_returns_typed_response():
    ledger = BudgetLedger(run_id="r1", ceiling_usd=10.0)
    fake = FakeClient(content="hello world", prompt_tokens=10, completion_tokens=5)

    resp = complete(
        [{"role": "user", "content": "hi"}],
        run_id="r1", ledger=ledger, client=fake,
    )

    assert isinstance(resp, LLMResponse)
    assert resp.text == "hello world"
    assert resp.model == MODELS["qwen"]  # default
    assert resp.input_tokens == 10
    assert resp.output_tokens == 5


def test_ledger_summary_breaks_down_models():
    ledger = BudgetLedger(run_id="r1", ceiling_usd=10.0)
    ledger.add(0.1, model="m1", input_tokens=10, output_tokens=5)
    ledger.add(0.2, model="m1", input_tokens=20, output_tokens=15)
    ledger.add(0.3, model="m2", input_tokens=30, output_tokens=25)

    summary = ledger.get_summary()
    assert summary["spent_usd"] == pytest.approx(0.6)
    assert summary["calls"] == 3
    assert summary["model_breakdown"]["m1"]["calls"] == 2
    assert summary["model_breakdown"]["m1"]["input_tokens"] == 30
    assert summary["model_breakdown"]["m2"]["spent_usd"] == pytest.approx(0.3)


def test_complete_unknown_model_costs_zero_and_does_not_charge_ledger():
    ledger = BudgetLedger(run_id="r1", ceiling_usd=10.0)
    fake = FakeClient(prompt_tokens=1000, completion_tokens=500)

    resp = complete(
        [{"role": "user", "content": "hi"}],
        model="some/uncharted-model",
        run_id="r1", ledger=ledger, client=fake,
    )

    assert resp.cost_usd == 0.0
    assert ledger.spent_usd == 0.0
    assert ledger.calls == 1  # call still counted


def test_complete_completes_call_then_blocks_next_when_over_ceiling():
    """Locks 'check before, add after' ordering: the call that crosses the
    ceiling completes; the next one is blocked before reaching the LLM.
    """
    ledger = BudgetLedger(run_id="r1", ceiling_usd=0.0005)  # below first-call cost
    fake = FakeClient(prompt_tokens=1000, completion_tokens=500)  # ~$0.000875

    # First call: ledger empty → check passes → call runs → ledger now over.
    resp1 = complete(
        [{"role": "user", "content": "first"}],
        model="anthropic/claude-haiku-4.5",
        run_id="r1", ledger=ledger, client=fake,
    )
    assert resp1.cost_usd == pytest.approx(0.000875)
    assert ledger.spent_usd > ledger.ceiling_usd

    # Second call: ledger over → check raises before LLM is touched.
    fake2 = FakeClient(prompt_tokens=1000, completion_tokens=500)
    with pytest.raises(BudgetExceededError):
        complete(
            [{"role": "user", "content": "second"}],
            model="anthropic/claude-haiku-4.5",
            run_id="r1", ledger=ledger, client=fake2,
        )
    assert fake2.last_kwargs is None  # second LLM call never dispatched
