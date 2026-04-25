"""Register confidence-aware agent and run treatment on retail dev slice.

Usage (from tau2-bench dir):
  uv run python "D:/TRP-1/week-10/Conversion Engine/eval/run_tau2_treatment.py" --smoke
  uv run python "D:/TRP-1/week-10/Conversion Engine/eval/run_tau2_treatment.py"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

CONV_ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CONV_ENGINE))

from eval.tau2_agent_runtime import ConfidenceAwareLLMAgent  # noqa: E402
from tau2.data_model.simulation import TextRunConfig  # noqa: E402
from tau2.registry import registry  # noqa: E402
from tau2.run import run_domain  # noqa: E402


def confidence_aware_factory(tools, domain_policy, **kwargs):
    return ConfidenceAwareLLMAgent(
        tools=tools,
        domain_policy=domain_policy,
        llm=kwargs.get("llm", "openrouter/qwen/qwen3-next-80b-a3b-thinking"),
        llm_args=kwargs.get("llm_args"),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="1 task, Qwen instruct model (~$0.02). Use to validate wrapper.",
    )
    args = parser.parse_args()

    registry.register_agent_factory(
        confidence_aware_factory, "confidence_aware_prompt"
    )

    # Same 30 task IDs the supplied baseline ran (Challenge_Documents/trace_log.jsonl)
    BASELINE_TASK_IDS = [
        "1", "2", "4", "7", "11", "15", "22", "24", "25", "29",
        "34", "43", "47", "48", "50", "52", "66", "72", "73", "76",
        "83", "85", "87", "92", "95", "104", "105", "106", "109", "113",
    ]

    config_kwargs = dict(
        domain="retail",
        agent="confidence_aware_prompt",
        num_trials=1,
        max_concurrency=4,
    )
    if args.smoke:
        model = "openrouter/qwen/qwen3-next-80b-a3b-instruct"
        config_kwargs["llm_agent"] = model
        config_kwargs["llm_user"] = model
        config_kwargs["task_ids"] = ["1"]
        config_kwargs["save_to"] = "conversion_engine_smoke"
    else:
        model = "openrouter/qwen/qwen3-next-80b-a3b-thinking"
        config_kwargs["llm_agent"] = model
        config_kwargs["llm_user"] = model
        config_kwargs["task_ids"] = BASELINE_TASK_IDS
        config_kwargs["save_to"] = "conversion_engine_treatment"

    config = TextRunConfig(**config_kwargs)
    results = run_domain(config)

    print(f"Done. Results in: data/simulations/{config_kwargs['save_to']}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
