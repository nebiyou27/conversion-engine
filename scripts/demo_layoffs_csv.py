"""Demo: load real layoffs.fyi CSV and emit Facts for one company.

Usage:
    python scripts/demo_layoffs_csv.py --company Meta
    python scripts/demo_layoffs_csv.py --company Meta --csv data/layoffs.csv
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.evidence.sources.layoffs import load_layoffs_csv_file


def _fact_to_dict(f) -> dict:
    if is_dataclass(f):
        return asdict(f)
    return dict(f.__dict__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Load layoffs.fyi CSV and emit Facts for a company.")
    parser.add_argument("--csv", default="data/layoffs.csv")
    parser.add_argument("--company", required=True, help="Company name to filter (case-insensitive).")
    parser.add_argument("--company-id", default=None, help="Defaults to lowercased company name.")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"CSV not found: {csv_path}", file=sys.stderr)
        return 2

    company_id = args.company_id or args.company.lower().replace(" ", "_")
    facts = load_layoffs_csv_file(
        str(csv_path),
        company_id=company_id,
        company_name=args.company,
    )

    print(f"Loaded {len(facts)} layoff fact(s) for {args.company} from {csv_path}")
    for fact in facts:
        print(json.dumps(_fact_to_dict(fact), default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
