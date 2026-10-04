"""Guided Learn capability — probe → plan → teach tutoring mode.

Methodology from amosblomqvist/learn: locate the learner's knowledge edge
first (probe), present a concrete teaching plan (plan), then teach from
unconditional truths with motivated, discoverable steps (teach).
"""

from __future__ import annotations

from typing import cast

from deeptutor.agents.chat.agentic_pipeline import AgenticChatPipeline
from deeptutor.core.capability_protocol import (
    CapabilityManifest,
    StreamBusProtocol,
    TurnCapability,
)
from deeptutor.core.context import UnifiedContext
from deeptutor.runtime.request_contracts import get_capability_request_schema
from deeptutor.runtime.stream_bus import StreamBus


class GuidedLearnCapability(TurnCapability):
    """Three-stage tutoring: probe the knowledge edge, plan, then teach."""

    manifest = CapabilityManifest(
        name="guided_learn",
        description=(
            "Guided learning: probe the learner's knowledge edge with diagnostic "
            "questions, present a teaching plan, then teach from unconditional "
            "truths with motivated, discoverable steps."
        ),
        stages=["probe", "plan", "teach"],
        tools_used=["ask_user"],
        cli_aliases=["learn", "guided"],
        request_schema=get_capability_request_schema("chat"),
    )

    async def run(self, context: UnifiedContext, stream: StreamBusProtocol) -> None:
        context.metadata["guided_learn_mode"] = True
        pipeline = AgenticChatPipeline(
            language=context.language,
            initial_tool_choice="ask_user",
        )
        await pipeline.run(context, cast(StreamBus, stream))


__all__ = ["GuidedLearnCapability"]
