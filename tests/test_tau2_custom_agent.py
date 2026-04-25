"""tau2-bench confidence-aware wrapper tests."""
from __future__ import annotations

from eval.tau2_custom_agent import (
    CONFIDENCE_THRESHOLD_FOR_IRREVERSIBLE,
    ConfidenceAwareAgent,
    VerificationResult,
    register,
)


def test_irreversible_low_confidence_action_asks_user():
    agent = ConfidenceAwareAgent()
    action = {
        "name": "cancel_order",
        "confidence": CONFIDENCE_THRESHOLD_FOR_IRREVERSIBLE - 0.1,
        "arguments": {"order_id": "ord_123"},
    }
    output = {"orders": [{"order_id": "ord_123", "status": "open"}]}

    assert agent.should_ask_instead_of_act(action, [output]) is True


def test_ambiguous_tool_output_asks_user_before_refund():
    agent = ConfidenceAwareAgent()
    action = {
        "name": "process_refund",
        "confidence": 0.95,
        "arguments": {"order_id": "ord_123"},
    }
    output = {
        "orders": [
            {"order_id": "ord_123", "status": "delivered"},
            {"order_id": "ord_456", "status": "delivered"},
        ]
    }

    assert agent.should_ask_instead_of_act(action, [output]) is True
    result = agent.verify_tool_output_matches_intent(action, output)
    assert result == VerificationResult(ok=False, confidence=0.4, reason="ambiguous_tool_output")


def test_missing_action_identifier_forces_replan():
    agent = ConfidenceAwareAgent()
    action = {
        "name": "modify_order",
        "confidence": 0.95,
        "arguments": {"order_id": "ord_999", "item_id": "item_1"},
    }
    output = {"order_id": "ord_123", "items": [{"item_id": "item_1"}]}

    result = agent.verify_tool_output_matches_intent(action, output)

    assert result.ok is False
    assert result.reason == "tool_output_missing_fields:order_id"


def test_verified_irreversible_action_can_proceed():
    agent = ConfidenceAwareAgent()
    action = {
        "name": "cancel_order",
        "confidence": 0.95,
        "arguments": {"order_id": "ord_123"},
    }
    output = {"order_id": "ord_123", "status": "open", "customer_id": "cust_1"}

    result = agent.verify_tool_output_matches_intent(action, output)
    decision = agent.guard_action(action, [output])

    assert result.ok is True
    assert result.reason == "verified"
    assert decision["decision"] == "act"


def test_reversible_action_bypasses_irreversible_gate():
    agent = ConfidenceAwareAgent()
    result = agent.verify_tool_output_matches_intent({"name": "lookup_order"}, None)

    assert result == VerificationResult(ok=True, confidence=1.0, reason="reversible_action")


def test_registry_hook_accepts_dict_registry():
    registry = {}

    register(registry)

    assert registry["confidence_aware_retail"] is ConfidenceAwareAgent
