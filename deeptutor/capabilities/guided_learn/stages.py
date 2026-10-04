"""Stage state machine for the Guided Learn capability.

Stages advance strictly in order: probe -> plan -> teach -> done.
The model signals a completed stage by ending its response with a
``[STAGE:<next>]`` marker line. The loop's ``finish_instruction`` hook
enforces the protocol: no marker, no turn finalization.
"""

from __future__ import annotations

import re

from deeptutor.core.context import UnifiedContext

STAGE_ORDER: tuple[str, ...] = ("probe", "plan", "teach")

# Terminal pseudo-stage: flow complete, system_block goes quiet.
DONE = "done"

# Marker must be on its own line at the end of the response.
STAGE_MARKER_RE = re.compile(r"^\[STAGE:(plan|teach|done)\]\s*$", re.MULTILINE)

# Checkpoint markers (teach stage): model judges each checkpoint.
CHECK_MARKER_RE = re.compile(r"^\[CHECK:(pass|fail)\]\s*$", re.MULTILINE)

# Misconception capture: model reports a found misconception for memory.
MISCONCEPTION_RE = re.compile(r"^\[MISCONCEPTION:(.+?)\]\s*$", re.MULTILINE)

# Legal transitions: current -> allowed next markers.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "probe": ("plan",),
    "plan": ("teach",),
    "teach": ("done",),
}

METADATA_KEY = "guided_learn_stage"


def current_stage(context: UnifiedContext) -> str:
    stage = (context.metadata or {}).get(METADATA_KEY, "probe")
    return stage if stage in (*STAGE_ORDER, DONE) else "probe"


def set_stage(context: UnifiedContext, stage: str) -> None:
    if context.metadata is None:
        context.metadata = {}
    context.metadata[METADATA_KEY] = stage


def extract_marker(text: str) -> str | None:
    """Return the stage marker at the end of *text*, if any."""
    match = STAGE_MARKER_RE.search(text)
    return match.group(1) if match else None


def strip_marker(text: str) -> str:
    """Remove protocol marker lines before showing text to the user."""
    text = STAGE_MARKER_RE.sub("", text)
    text = CHECK_MARKER_RE.sub("", text)
    text = MISCONCEPTION_RE.sub("", text)
    return text.strip()


def extract_check(text: str) -> str | None:
    """Return the checkpoint verdict ('pass'/'fail') at the end of *text*."""
    match = CHECK_MARKER_RE.search(text)
    return match.group(1) if match else None


def extract_misconceptions(text: str) -> list[str]:
    """Return misconception descriptions reported in *text*."""
    return [m.group(1).strip() for m in MISCONCEPTION_RE.finditer(text)]


__all__ = [
    "METADATA_KEY",
    "STAGE_ORDER",
    "TRANSITIONS",
    "current_stage",
    "extract_check",
    "extract_marker",
    "extract_misconceptions",
    "set_stage",
    "strip_marker",
]
