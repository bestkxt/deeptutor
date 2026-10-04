"""Persistent misconception memory for Guided Learn.

Stores the learner's known misconceptions as JSON so future probe stages
can target them first. Resolves through DeepTutor's PathService when
available, falling back to ~/.local/share/deeptutor/.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def _store_path() -> Path:
    try:
        from deeptutor.services.path_service import get_path_service

        root = Path(get_path_service().user_data_dir)
    except Exception:
        root = Path.home() / ".local" / "share" / "deeptutor"
    path = root / "guided_learn_misconceptions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_misconceptions(limit: int = 10) -> list[dict[str, Any]]:
    """Return the most recent misconceptions, newest first."""
    path = _store_path()
    if not path.exists():
        return []
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(items, list):
        return []
    return items[:limit]


def save_misconception(description: str, topic: str = "") -> None:
    """Append a misconception, deduplicating on normalized description."""
    description = description.strip()
    if not description:
        return
    path = _store_path()
    items: list[dict[str, Any]] = []
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                items = loaded
        except (json.JSONDecodeError, OSError):
            items = []
    norm = description.lower()
    if any(m.get("description", "").lower() == norm for m in items):
        return
    items.insert(0, {"description": description, "topic": topic, "ts": int(time.time())})
    path.write_text(json.dumps(items[:100], ensure_ascii=False, indent=1), encoding="utf-8")


def format_for_prompt(items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    lines = ["该学生已知的历史错误观念（探查时优先验证是否仍然存在）："]
    for m in items:
        topic = f"【{m['topic']}】" if m.get("topic") else ""
        lines.append(f"- {topic}{m['description']}")
    return "\n".join(lines)


__all__ = ["format_for_prompt", "load_misconceptions", "save_misconception"]
