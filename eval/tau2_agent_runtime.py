"""Prompt-only tau2 runtime for the confidence-aware mechanism.

This adapter intentionally keeps the first-pass mechanism in the system prompt.
The helper rules in ``eval.tau2_custom_agent`` remain the unit-tested validation
harness, but this runtime does not import them or intercept tool calls.
"""
from __future__ import annotations

from typing import Any, TypeVar

try:  # pragma: no cover - exercised in the tau2 virtualenv.
    from tau2.agent.llm_agent import LLMAgent, LLMAgentState  # type: ignore
except Exception:  # pragma: no cover - local repo does not vendor tau2.
    try:
        from tau2.agents.llm_agent import LLMAgent, LLMAgentState  # type: ignore
    except Exception:
        LLMAgentState = TypeVar("LLMAgentState")  # type: ignore

        class LLMAgent:  # type: ignore[no-redef]
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                self.domain_policy = kwargs.get("domain_policy", "")

            def __class_getitem__(cls, _item: Any) -> type["LLMAgent"]:
                return cls


CONFIDENCE_AWARE_INSTRUCTION = """\
Use signal-confidence-aware action selection.
Before any irreversible or customer-state-changing action, verify that the
latest tool output uniquely supports the action arguments and the user's stated
intent. If the tool output is ambiguous, missing the relevant identifier, or
shows multiple plausible matches, ask one concise clarifying question instead
of committing. For reversible lookups, continue normally. Do not over-ask when
the tool evidence is unique and sufficient.
"""

CONFIDENCE_AWARE_SYSTEM = """\
You are a retail support agent operating under this domain policy:

{domain_policy}

Additional mechanism instruction:

{agent_instruction}
"""


class ConfidenceAwareLLMAgent(LLMAgent[LLMAgentState]):
    """tau2 LLMAgent variant that injects verification guidance by prompt only."""

    @property
    def system_prompt(self) -> str:
        return CONFIDENCE_AWARE_SYSTEM.format(
            agent_instruction=CONFIDENCE_AWARE_INSTRUCTION,
            domain_policy=getattr(self, "domain_policy", ""),
        )


def create_agent(*args: Any, **kwargs: Any) -> ConfidenceAwareLLMAgent:
    return ConfidenceAwareLLMAgent(*args, **kwargs)


def agent_factory(*args: Any, **kwargs: Any) -> ConfidenceAwareLLMAgent:
    return create_agent(*args, **kwargs)


def register(registry: Any) -> None:
    if hasattr(registry, "register"):
        registry.register("confidence_aware_prompt", ConfidenceAwareLLMAgent)
    elif isinstance(registry, dict):
        registry["confidence_aware_prompt"] = ConfidenceAwareLLMAgent
    else:
        raise TypeError("registry must expose register(name, cls) or be a dict")

