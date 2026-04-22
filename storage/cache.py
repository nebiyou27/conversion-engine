"""File-based JSON cache for enrichment results.

Keyed by (source, query) tuple. Stored as JSON under `data/cache/` for inspectability.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

DEFAULT_CACHE_DIR = Path("data") / "cache"


def _key_hash(source: str, query: str) -> str:
    return hashlib.sha256(f"{source}::{query}".encode("utf-8")).hexdigest()[:16]


def _path_for(source: str, query: str, cache_dir: Path) -> Path:
    return cache_dir / f"{source}_{_key_hash(source, query)}.json"


def get(source: str, query: str, cache_dir: Path = DEFAULT_CACHE_DIR) -> dict | None:
    path = _path_for(source, query, cache_dir)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def put(source: str, query: str, value: dict, cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _path_for(source, query, cache_dir)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")
