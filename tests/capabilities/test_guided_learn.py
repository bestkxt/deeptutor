"""Tests for the Guided Learn capability (probe → plan → teach).

Covers the stage state machine, checkpoint gate, misconception memory,
prompt content, and registration. Uses real UnifiedContext throughout.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeptutor.capabilities.guided_learn.capability import GuidedLearnCapability
from deeptutor.capabilities.guided_learn.loop import GuidedLearnLoopCapability
from deeptutor.capabilities.guided_learn.memory import (
    load_misconceptions,
    save_misconception,
)
from deeptutor.capabilities.guided_learn.stages import (
    current_stage,
    extract_check,
    extract_marker,
    extract_misconceptions,
    set_stage,
    strip_marker,
)
from deeptutor.core.context import UnifiedContext


def _context(**metadata) -> UnifiedContext:
    base = {"guided_learn_mode": True}
    base.update(metadata)
    return UnifiedContext(
        user_message="我想学贝叶斯定理",
        session_id="session-gl-1",
        metadata=base,
        language="zh",
    )


@pytest.fixture()
def loop() -> GuidedLearnLoopCapability:
    return GuidedLearnLoopCapability()


@pytest.fixture()
def ctx() -> UnifiedContext:
    return _context()


# ---------------------------------------------------------------------------
# Stage marker parsing
# ---------------------------------------------------------------------------


class TestMarkerParsing:
    def test_extract_stage_marker(self):
        assert extract_marker("结论\n[STAGE:plan]") == "plan"
        assert extract_marker("[STAGE:teach]") == "teach"
        assert extract_marker("[STAGE:done]") == "done"

    def test_marker_must_be_own_line_at_end(self):
        assert extract_marker("xxx [STAGE:plan] yyy") is None
        assert extract_marker("[STAGE:plan]\n还有后续文字") is None

    def test_invalid_marker_names_rejected(self):
        assert extract_marker("[STAGE:foo]") is None
        assert extract_marker("[stage:plan]") is None  # case-sensitive
        assert extract_marker("[STAGE:PLAN]") is None

    def test_extract_check(self):
        assert extract_check("讲完了\n[CHECK:pass]") == "pass"
        assert extract_check("没过\n[CHECK:fail]") == "fail"
        assert extract_check("没有标记") is None

    def test_extract_misconceptions(self):
        text = "总结\n[MISCONCEPTION: 忽视基础概率]\n[MISCONCEPTION: 混淆条件概率方向]"
        found = extract_misconceptions(text)
        assert found == ["忽视基础概率", "混淆条件概率方向"]

    def test_strip_removes_all_markers(self):
        text = "正文\n[CHECK:fail]\n[MISCONCEPTION: x]\n[STAGE:plan]"
        assert strip_marker(text) == "正文"

    def test_strip_leaves_normal_text(self):
        assert strip_marker("普通回复，没有标记。") == "普通回复，没有标记。"


# ---------------------------------------------------------------------------
# Stage state machine
# ---------------------------------------------------------------------------


class TestStageMachine:
    def test_initial_stage_is_probe(self, ctx):
        assert current_stage(ctx) == "probe"

    def test_unknown_stage_falls_back_to_probe(self):
        ctx = _context(guided_learn_stage="bogus")
        assert current_stage(ctx) == "probe"

    def test_set_and_get_stage(self, ctx):
        set_stage(ctx, "teach")
        assert current_stage(ctx) == "teach"

    def test_legal_transitions(self, loop, ctx):
        assert loop.finish_instruction(ctx, "探查结论\n[STAGE:plan]") is None
        assert current_stage(ctx) == "plan"
        assert loop.finish_instruction(ctx, "计划\n[STAGE:teach]") is None
        assert current_stage(ctx) == "teach"
        assert loop.finish_instruction(ctx, "讲完\n[STAGE:done]") is None
        assert current_stage(ctx) == "done"
        assert ctx.metadata["guided_learn_complete"] is True

    @pytest.mark.parametrize(
        "stage,bad_marker",
        [
            ("probe", "teach"),
            ("probe", "done"),
            ("plan", "plan"),
            ("plan", "done"),
            ("teach", "plan"),
        ],
    )
    def test_illegal_transitions_blocked(self, loop, stage, bad_marker):
        ctx = _context(guided_learn_stage=stage)
        instr = loop.finish_instruction(ctx, f"内容\n[STAGE:{bad_marker}]")
        assert instr is not None
        assert "非法" in instr
        assert current_stage(ctx) == stage  # stage unchanged

    def test_missing_marker_blocks_finalize(self, loop, ctx):
        instr = loop.finish_instruction(ctx, "我直接开讲贝叶斯定理……")
        assert instr is not None
        assert "[STAGE:plan]" in instr

    def test_inactive_mode_is_inert(self, loop):
        ctx = UnifiedContext(user_message="hi", session_id="s", metadata={})
        assert loop.finish_instruction(ctx, "anything") is None
        assert loop.system_block(ctx, language="zh", prompts={}) is None


# ---------------------------------------------------------------------------
# Stage-aware prompts
# ---------------------------------------------------------------------------


class TestStagePrompts:
    def test_probe_prompt_isolated(self, loop, ctx):
        block = loop.system_block(ctx, language="zh", prompts={})
        assert "探查" in block.content
        assert "不许讲授新知识" in block.content
        # Later stages must not leak into the probe prompt.
        assert "[STAGE:teach]" not in block.content

    def test_plan_prompt_after_transition(self, loop, ctx):
        set_stage(ctx, "plan")
        block = loop.system_block(ctx, language="zh", prompts={})
        assert "ask_user" in block.content  # confirmation required
        assert "探查" not in block.content or "基于探查" in block.content

    def test_teach_prompt_has_checkpoint_protocol(self, loop, ctx):
        set_stage(ctx, "teach")
        block = loop.system_block(ctx, language="zh", prompts={})
        assert "[CHECK:pass]" in block.content
        assert "[CHECK:fail]" in block.content

    def test_done_stage_goes_quiet(self, loop, ctx):
        set_stage(ctx, "done")
        assert loop.system_block(ctx, language="zh", prompts={}) is None

    def test_english_prompts_exist(self, loop, ctx):
        ctx.language = "en"
        for stage in ("probe", "plan", "teach"):
            set_stage(ctx, stage)
            block = loop.system_block(ctx, language="en", prompts={})
            assert block is not None and len(block.content) > 200


# ---------------------------------------------------------------------------
# Checkpoint gate
# ---------------------------------------------------------------------------


class TestCheckpointGate:
    def test_first_fail_allows_finalize(self, loop, ctx):
        set_stage(ctx, "teach")
        assert loop.finish_instruction(ctx, "换讲法重讲\n[CHECK:fail]") is None
        assert ctx.metadata["guided_learn_fails"] == 1

    def test_second_consecutive_fail_forces_reteach(self, loop, ctx):
        set_stage(ctx, "teach")
        ctx.metadata["guided_learn_fails"] = 1
        instr = loop.finish_instruction(ctx, "又没过\n[CHECK:fail]")
        assert instr is not None
        assert "完全不同" in instr
        assert ctx.metadata["guided_learn_fails"] == 0  # counter reset

    def test_pass_resets_counter(self, loop, ctx):
        set_stage(ctx, "teach")
        ctx.metadata["guided_learn_fails"] = 1
        assert loop.finish_instruction(ctx, "答对了\n[CHECK:pass]") is None
        assert ctx.metadata["guided_learn_fails"] == 0

    def test_check_alone_is_valid_mid_teach_round(self, loop, ctx):
        # A checkpoint verdict without a stage marker must not be blocked.
        set_stage(ctx, "teach")
        assert loop.finish_instruction(ctx, "继续讲\n[CHECK:pass]") is None

    def test_check_and_stage_marker_together(self, loop, ctx):
        set_stage(ctx, "teach")
        assert (
            loop.finish_instruction(ctx, "全部讲完\n[CHECK:pass]\n[STAGE:done]")
            is None
        )
        assert current_stage(ctx) == "done"


# ---------------------------------------------------------------------------
# Misconception memory
# ---------------------------------------------------------------------------


class TestMisconceptionMemory:
    @pytest.fixture()
    def isolated_home(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        # Force fallback path (no PathService in test env).
        monkeypatch.setattr(
            "deeptutor.capabilities.guided_learn.memory._store_path",
            lambda: tmp_path / "misconceptions.json",
        )

    def test_save_load_roundtrip(self, isolated_home):
        save_misconception("忽视基础概率", topic="贝叶斯定理")
        items = load_misconceptions()
        assert len(items) == 1
        assert items[0]["description"] == "忽视基础概率"
        assert items[0]["topic"] == "贝叶斯定理"

    def test_dedup(self, isolated_home):
        save_misconception("忽视基础概率")
        save_misconception("忽视基础概率")
        assert len(load_misconceptions()) == 1

    def test_empty_description_ignored(self, isolated_home):
        save_misconception("   ")
        assert load_misconceptions() == []

    def test_corrupt_file_returns_empty(self, isolated_home, tmp_path):
        (tmp_path / "misconceptions.json").write_text("not json{{{")
        assert load_misconceptions() == []

    def test_markers_captured_and_stripped(self, loop, ctx, isolated_home):
        out = loop.final_text_override(
            ctx, "总结\n[MISCONCEPTION: 混淆P(A|B)方向]\n[STAGE:plan]"
        )
        assert "[MISCONCEPTION" not in out
        assert "[STAGE" not in out
        assert any("混淆" in m["description"] for m in load_misconceptions())

    def test_known_misconceptions_injected_into_probe(
        self, loop, ctx, isolated_home
    ):
        save_misconception("忽视基础概率", topic="贝叶斯定理")
        block = loop.system_block(ctx, language="zh", prompts={})
        assert "忽视基础概率" in block.content
        assert "历史错误观念" in block.content

    def test_no_injection_when_empty(self, loop, ctx, isolated_home):
        block = loop.system_block(ctx, language="zh", prompts={})
        assert "历史错误观念" not in block.content


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_manifest(self):
        m = GuidedLearnCapability.manifest
        assert m.name == "guided_learn"
        assert m.stages == ["probe", "plan", "teach"]
        assert set(m.cli_aliases) == {"learn", "guided"}

    def test_bootstrap_registration(self):
        from deeptutor.runtime.bootstrap.builtin_capabilities import (
            BUILTIN_CAPABILITY_CLASSES,
            BUILTIN_CAPABILITY_SPECS,
        )

        assert "guided_learn" in BUILTIN_CAPABILITY_CLASSES
        assert "guided_learn" in BUILTIN_CAPABILITY_SPECS
        spec = BUILTIN_CAPABILITY_SPECS["guided_learn"]
        assert spec.manifest.stages == ["probe", "plan", "teach"]

    def test_loop_registry_registration(self):
        from deeptutor.capabilities.registry import BUILTIN_LOOP_CAPABILITY_SPECS

        names = [s.name for s in BUILTIN_LOOP_CAPABILITY_SPECS]
        assert "guided_learn" in names
        # The spec must actually instantiate.
        spec = next(s for s in BUILTIN_LOOP_CAPABILITY_SPECS if s.name == "guided_learn")
        assert isinstance(spec.create(), GuidedLearnLoopCapability)
