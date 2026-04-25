"""Convert tau2 saved results to the required trace JSONL shape."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


TRACE_KEYS = (
    "agent_cost",
    "domain",
    "duration",
    "reward",
    "simulation_id",
    "task_id",
    "termination_reason",
)


def _iter_json_objects(path: Path) -> Iterable[Any]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return
    if text.startswith("{") or text.startswith("["):
        yield json.loads(text)
        return
    for line in text.splitlines():
        line = line.strip()
        if line:
            yield json.loads(line)


def _find_records(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        if {"reward", "task_id"}.issubset(value):
            yield value
            return
        for key in ("simulations", "results", "records", "traces", "episodes"):
            nested = value.get(key)
            if nested is not None:
                yield from _find_records(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _find_records(item)


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: record.get(key) for key in TRACE_KEYS}


def convert(input_path: Path, output_path: Path) -> int:
    records: list[dict[str, Any]] = []
    for obj in _iter_json_objects(input_path):
        records.extend(normalize_record(record) for record in _find_records(obj))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path, default=Path("deliverables/held_out_traces.jsonl"))
    args = parser.parse_args()
    count = convert(args.input, args.out)
    print(f"wrote {count} records to {args.out}")


if __name__ == "__main__":
    main()

