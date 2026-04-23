"""Run one complete synthetic prospect thread."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.runtime import configure_logging
from agent.core import run_synthetic_thread


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description="Run one synthetic prospect thread.")
    parser.add_argument("--fixture", default="data/fixtures/companies/acme_series_b.json")
    parser.add_argument("--output-root", default="outputs/runs")
    parser.add_argument("--live", action="store_true", help="Use live integrations when configured.")
    args = parser.parse_args()

    result = run_synthetic_thread(
        fixture_path=Path(args.fixture),
        output_root=Path(args.output_root),
        live=args.live,
    )
    print(result.run_dir)
    print(result.gate_report["decision"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
