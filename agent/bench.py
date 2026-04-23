"""Bench loader — internal capacity, read-only.

Bench is Tenacious's own capacity snapshot, not prospect evidence. It lives
outside the evidence/claims epistemic flow: availability is a fact the gate
and actions layers cite directly (R8). The loader is a thin data reader with
a narrow filter — committed stacks are not available regardless of headcount.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BENCH_PATH = (
    Path("Challenge_Documents") / "tenacious_sales_data" / "seed" / "bench_summary.json"
)


class BenchFormatError(ValueError):
    """Bench file missing, unreadable, or malformed."""


@dataclass(frozen=True)
class Stack:
    name: str
    available_engineers: int
    skill_subsets: tuple[str, ...]
    time_to_deploy_days: int
    note: str | None

    @property
    def committed(self) -> bool:
        return bool(self.note) and "committed" in self.note.lower()


@dataclass(frozen=True)
class BenchSummary:
    as_of: str
    total_on_bench: int
    stacks: tuple[Stack, ...]

    def available_stacks(self) -> tuple[Stack, ...]:
        return tuple(s for s in self.stacks if s.available_engineers > 0 and not s.committed)

    def stack(self, name: str) -> Stack | None:
        for s in self.stacks:
            if s.name == name:
                return s
        return None


def load_bench(path: Path | str = DEFAULT_BENCH_PATH) -> BenchSummary:
    p = Path(path)
    if not p.exists():
        raise BenchFormatError(f"bench file not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise BenchFormatError(f"bench file is not valid JSON: {e}") from e

    required = ("as_of", "stacks", "total_engineers_on_bench")
    missing = [k for k in required if k not in data]
    if missing:
        raise BenchFormatError(f"bench file missing keys: {missing}")

    raw_stacks = data["stacks"]
    if not isinstance(raw_stacks, dict):
        raise BenchFormatError("bench.stacks must be a dict")

    stacks: list[Stack] = []
    for name, body in raw_stacks.items():
        if not isinstance(body, dict):
            raise BenchFormatError(f"bench.stacks.{name} must be a dict")
        if "available_engineers" not in body:
            raise BenchFormatError(f"bench.stacks.{name} missing available_engineers")
        stacks.append(Stack(
            name=name,
            available_engineers=int(body["available_engineers"]),
            skill_subsets=tuple(body.get("skill_subsets", [])),
            time_to_deploy_days=int(body.get("time_to_deploy_days", 0)),
            note=body.get("note"),
        ))

    return BenchSummary(
        as_of=data["as_of"],
        total_on_bench=int(data["total_engineers_on_bench"]),
        stacks=tuple(stacks),
    )
