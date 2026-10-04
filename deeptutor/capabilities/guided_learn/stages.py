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
    """Remove the protocol marker line before showing text to the user."""
    return STAGE_MARKER_RE.sub("", text).strip()


__all__ = [
    "METADATA_KEY",
    "STAGE_ORDER",
    "TRANSITIONS",
    "current_stage",
    "extract_marker",
    "set_stage",
    "strip_marker",
]
