from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_seen_urls(path: Path) -> set[str]:
    if not path.exists():
        return set()

    content = json.loads(path.read_text(encoding="utf-8"))
    return {str(item) for item in content}


def save_seen_urls(path: Path, seen_urls: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(path, sorted(seen_urls))


def read_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(path, payload)


def _write_json(path: Path, payload: Any) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)

