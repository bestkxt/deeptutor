"""Chat-loop hooks for the Guided Learn capability.

Implements the probe -> plan -> teach stage state machine:

- ``system_block`` injects only the *current* stage's prompt (identity +
  stage instructions), so the model cannot see or jump to later stages.
- ``finish_instruction`` enforces the protocol: a turn may only finalize
  when the model ends with a legal ``[STAGE:<next>]`` marker. The marker
  advances ``guided_learn_stage`` in turn metadata.
- ``final_text_override`` strips the protocol marker before display.
"""

from __future__ import annotations

from importlib import resources
from typing import Any

from deeptutor.capabilities.guided_learn.stages import (
    TRANSITIONS,
    current_stage,
    extract_marker,
    set_stage,
    strip_marker,
)
from deeptutor.capabilities.protocol import PromptBlock
from deeptutor.core.context import UnifiedContext


class GuidedLearnLoopCapability:
    """Stage-gated probe → plan → teach tutoring policy."""

    name = "guided_learn"
    owned_tools: tuple[str, ...] = ()

    def is_active(self, context: UnifiedContext) -> bool:
        return bool(context.metadata.get("guided_learn_mode"))

    def system_block(
        self,
        context: UnifiedContext,
        *,
        language: str,
        prompts: dict[str, Any],
    ) -> PromptBlock | None:
        _ = prompts
        if not self.is_active(context):
            return None
        stage = current_stage(context)
        if stage not in TRANSITIONS:
            return None
        identity = _load_prompt(language, "identity")
        stage_prompt = _load_prompt(language, stage)
        return PromptBlock("guided_learn", f"{identity}\n\n{stage_prompt}")

    def augment_kwargs(
        self,
        tool_name: str,
        kwargs: dict[str, Any],
        context: UnifiedContext,
    ) -> dict[str, Any]:
        _ = tool_name, context
        return kwargs

    def pre_loop_seed(self, context: UnifiedContext) -> str:
        _ = context
        return ""

    def finish_instruction(
        self, context: UnifiedContext, final_text: str
    ) -> str | None:
        """Enforce the stage protocol before the turn may finalize."""
        if not self.is_active(context):
            return None
        stage = current_stage(context)
        marker = extract_marker(final_text)
        if marker is None:
            return (
                f"协议要求：你当前处于「{stage}」阶段，本轮不能直接结束。"
                f"请按本阶段的阶段结束条件完成任务，并在回复最后单独一行写"
                f"合法的阶段标记（本阶段允许：{', '.join('[STAGE:' + m + ']' for m in TRANSITIONS[stage])}）。"
            )
        if marker not in TRANSITIONS[stage]:
            return (
                f"非法的阶段跳转：当前是「{stage}」阶段，不允许直接跳到 [STAGE:{marker}]。"
                f"本阶段允许的标记：{', '.join('[STAGE:' + m + ']' for m in TRANSITIONS[stage])}。"
                f"请按当前阶段指令继续。"
            )
        # Legal transition: advance the stage and let the turn finalize.
        # The next turn's system_block will inject the next stage's prompt.
        # "done" is not in TRANSITIONS, so system_block goes quiet afterwards.
        set_stage(context, marker)
        if marker == "done":
            context.metadata["guided_learn_complete"] = True
        return None

    def final_text_override(
        self, context: UnifiedContext, final_text: str
    ) -> str:
        _ = context
        return strip_marker(final_text)


def _load_prompt(language: str, name: str) -> str:
    lang = "zh" if language.lower().startswith("zh") else "en"
    prompt = resources.files(__package__).joinpath("prompts", lang, f"{name}.md")
    return prompt.read_text(encoding="utf-8").strip()


__all__ = ["GuidedLearnLoopCapability"]
