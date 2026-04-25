"""Confidence-aware tau2-bench agent wrapper.

The production mechanism in this repo is signal-confidence-aware phrasing:
claims must clear a tiered evidence gate before they can be stated with
confidence. This module maps the same idea onto tau2 retail tasks: actions
that mutate customer state must clear a tool-output verification gate before
the agent commits them.

The tau2 package is intentionally optional here so the file remains importable
in the project test suite. In a tau2 environment, pass an existing retail agent
instance into ``ConfidenceAwareAgent(base_agent=...)`` or reference the class by
module path from the tau2 CLI.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:  # pragma: no cover - exercised only when tau2-bench is installed.
    from tau2.agents.base import BaseAgent  # type: ignore
except Exception:  # pragma: no cover - local repo does not vendor tau2.

    class BaseAgent:  # type: ignore[no-redef]
        """Fallback base class so local imports do not require tau2."""


CONFIDENCE_THRESHOLD_FOR_IRREVERSIBLE = 0.8
VERIFICATION_REQUIRED_ACTIONS = {"cancel_order", "process_refund", "modify_order"}
AMBIGUITY_MARKERS = {
    "ambiguous",
    "multiple matches",
    "multiple customers",
    "multiple orders",
    "not found",
    "missing",
    "unknown",
    "unclear",
    "no matching",
}
REQUIRED_FIELD_MARKERS = {"order_id", "customer_id", "item_id"}


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of checking whether an action is grounded in tool output."""

    ok: bool
    confidence: float
    reason: str


def _read_field(value: Any, field: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(field, default)
    return getattr(value, field, default)


def _action_name(action: Any) -> str:
    if isinstance(action, str):
        return action
    name = _read_field(action, "name") or _read_field(action, "tool_name")
    if name:
        return str(name)
    if isinstance(action, dict) and len(action) == 1:
        return str(next(iter(action)))
    return ""


def _action_arguments(action: Any) -> dict[str, Any]:
    if isinstance(action, dict):
        args = action.get("arguments") or action.get("args") or action.get("parameters")
        if isinstance(args, dict):
            return args
        name = _action_name(action)
        nested = action.get(name)
        if isinstance(nested, dict):
            return nested
    for field in ("arguments", "args", "parameters"):
        args = _read_field(action, field)
        if isinstance(args, dict):
            return args
    return {}


def _stringify_tool_output(tool_output: Any) -> str:
    if tool_output is None:
        return ""
    if isinstance(tool_output, str):
        return tool_output.lower()
    return repr(tool_output).lower()


def _confidence_from_action(action: Any) -> float:
    raw = _read_field(action, "confidence", None)
    if raw is None and isinstance(action, dict):
        raw = action.get("score")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 1.0
    return min(1.0, max(0.0, value))


def _latest_tool_output(recent_tool_outputs: list[Any] | tuple[Any, ...] | None) -> Any:
    if not recent_tool_outputs:
        return None
    return recent_tool_outputs[-1]


def _output_has_multiple_matches(tool_output: Any) -> bool:
    if isinstance(tool_output, dict):
        for key in ("matches", "orders", "customers", "items", "results"):
            value = tool_output.get(key)
            if isinstance(value, list) and len(value) > 1:
                return True
    if isinstance(tool_output, list):
        return len(tool_output) > 1
    text = _stringify_tool_output(tool_output)
    return any(marker in text for marker in AMBIGUITY_MARKERS)


def _action_fields_missing_from_output(action: Any, tool_output: Any) -> list[str]:
    args = _action_arguments(action)
    if not args:
        return []
    text = _stringify_tool_output(tool_output)
    missing: list[str] = []
    for field, value in args.items():
        if field not in REQUIRED_FIELD_MARKERS and not field.endswith("_id"):
            continue
        if value is None or str(value).strip() == "":
            missing.append(field)
            continue
        if str(value).lower() not in text:
            missing.append(field)
    return missing


class ConfidenceAwareAgent(BaseAgent):
    """Verification-before-commit wrapper for tau2-bench retail agents."""

    confidence_threshold = CONFIDENCE_THRESHOLD_FOR_IRREVERSIBLE
    verification_required_actions = VERIFICATION_REQUIRED_ACTIONS

    def __init__(self, *args: Any, base_agent: Any = None, **kwargs: Any) -> None:
        self.base_agent = base_agent
        if base_agent is None:
            try:
                super().__init__(*args, **kwargs)
            except TypeError:
                # Some tau2 BaseAgent variants are protocol-like and take no
                # constructor args. Keep this wrapper permissive for registry use.
                super().__init__()

    def __getattr__(self, name: str) -> Any:
        if self.base_agent is not None:
            return getattr(self.base_agent, name)
        raise AttributeError(name)

    def should_ask_instead_of_act(
        self,
        proposed_action: Any,
        recent_tool_outputs: list[Any] | tuple[Any, ...] | None,
    ) -> bool:
        """Return True when the safer next step is asking the user."""

        name = _action_name(proposed_action)
        latest_output = _latest_tool_output(recent_tool_outputs)
        confidence = _confidence_from_action(proposed_action)

        if name in self.verification_required_actions and confidence < self.confidence_threshold:
            return True
        if _output_has_multiple_matches(latest_output):
            return True
        if _action_fields_missing_from_output(proposed_action, latest_output):
            return True
        return False

    def verify_tool_output_matches_intent(self, action: Any, tool_output: Any) -> VerificationResult:
        """Check that the latest tool output supports the proposed action."""

        name = _action_name(action)
        if name not in self.verification_required_actions:
            return VerificationResult(ok=True, confidence=1.0, reason="reversible_action")

        confidence = _confidence_from_action(action)
        if confidence < self.confidence_threshold:
            return VerificationResult(ok=False, confidence=confidence, reason="low_action_confidence")

        if tool_output is None:
            return VerificationResult(ok=False, confidence=0.0, reason="missing_tool_output")

        if _output_has_multiple_matches(tool_output):
            return VerificationResult(ok=False, confidence=0.4, reason="ambiguous_tool_output")

        missing = _action_fields_missing_from_output(action, tool_output)
        if missing:
            return VerificationResult(
                ok=False,
                confidence=0.5,
                reason=f"tool_output_missing_fields:{','.join(sorted(missing))}",
            )

        return VerificationResult(ok=True, confidence=confidence, reason="verified")

    def guard_action(self, action: Any, recent_tool_outputs: list[Any] | tuple[Any, ...] | None) -> dict[str, Any]:
        """Small adapter surface for tau2 registries or custom loops."""

        latest_output = _latest_tool_output(recent_tool_outputs)
        verification = self.verify_tool_output_matches_intent(action, latest_output)
        if verification.ok:
            return {"decision": "act", "action": action, "verification": verification}
        if self.should_ask_instead_of_act(action, recent_tool_outputs):
            return {
                "decision": "ask_user",
                "message": "I found more than one possible match. Which one should I use?",
                "verification": verification,
            }
        return {"decision": "replan", "verification": verification}


def register(registry: Any) -> None:
    """Best-effort registry hook for tau2 installations that expose a registry."""

    if hasattr(registry, "register"):
        registry.register("confidence_aware_retail", ConfidenceAwareAgent)
    elif isinstance(registry, dict):
        registry["confidence_aware_retail"] = ConfidenceAwareAgent
    else:
        raise TypeError("registry must expose register(name, cls) or be a dict")


AGENT_REGISTRY = {"confidence_aware_retail": ConfidenceAwareAgent}
