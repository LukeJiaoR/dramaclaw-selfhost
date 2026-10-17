from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_optimize_voice_description_uses_dedicated_gateway_model(monkeypatch):
    from novelvideo import config
    from novelvideo import voice_design

    captured: dict[str, object] = {}

    class FakeAgent:
        def __init__(self, model, **kwargs):
            captured["model"] = model
            captured["agent_kwargs"] = kwargs

        async def run(self, task: str):
            captured["task"] = task
            return SimpleNamespace(output="“青年男性，清亮偏低的声线，语速从容，咬字清晰。”")

    def fake_model(model_env: str, default_model: str, **kwargs):
        captured["model_env"] = model_env
        captured["default_model"] = default_model
        captured["model_kwargs"] = kwargs
        return "gateway-model"

    monkeypatch.setattr(config, "get_newapi_text_pydantic_model", fake_model)
    monkeypatch.setattr(voice_design, "Agent", FakeAgent)

    result = await voice_design.optimize_voice_description(
        description="年轻男声",
        preview_text="今晚必须离开这里。",
        subject_context="角色：祁南\n角色设定：冷静克制",
    )

    assert result == "青年男性，清亮偏低的声线，语速从容，咬字清晰。"
    assert captured["model_env"] == "VOICE_PROMPT_OPTIMIZER_MODEL"
    assert captured["default_model"] == "brainclaw"
    assert "角色：祁南" in str(captured["task"])
    assert "今晚必须离开这里" in str(captured["task"])


@pytest.mark.asyncio
async def test_optimize_voice_description_rejects_empty_input():
    from novelvideo.voice_design import optimize_voice_description

    with pytest.raises(ValueError, match="请先填写声线描述"):
        await optimize_voice_description(description=" ", subject_context="旁白")


def test_voice_model_defaults_preserve_official_and_advanced_modes():
    from novelvideo.official_defaults import (
        ADVANCED_TEXT_MODEL_BY_ENV, DEFAULT_TEXT_MODEL_BY_ENV,
    )
    assert DEFAULT_TEXT_MODEL_BY_ENV["VOICE_PROMPT_OPTIMIZER_MODEL"] == "brainclaw"
    assert ADVANCED_TEXT_MODEL_BY_ENV["VOICE_PROMPT_OPTIMIZER_MODEL"] == "DC-voice-prompt-optimizer-LLM"
