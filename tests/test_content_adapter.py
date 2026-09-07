from __future__ import annotations

from types import SimpleNamespace

import pytest

from novelvideo.models import NovelEpisode
from novelvideo.sqlite_store import SQLiteStore, load_episode_planning_content

pytestmark = pytest.mark.m03


@pytest.mark.asyncio
async def test_adapted_content_overrides_raw_working_content(tmp_path) -> None:
    output_dir = tmp_path / "output" / "admin" / "demo"
    state_dir = tmp_path / "state" / "admin" / "demo"
    store = SQLiteStore(
        "admin/demo", output_dir=str(output_dir), state_dir=str(state_dir)
    )
    try:
        await store.initialize()
        await store.add_episodes(
            [
                NovelEpisode(
                    number=1,
                    title="第一集",
                    raw_content="原文第一行\n原文第二行",
                )
            ]
        )

        assert await store.load_working_content(1) == "原文第一行\n原文第二行"

        await store.save_adapted_content(1, "改写第一行\n改写第二行")

        assert await store.load_adapted_content(1) == "改写第一行\n改写第二行"
        assert await store.load_working_content(1) == "改写第一行\n改写第二行"
        assert (
            await load_episode_planning_content(
                store,
                NovelEpisode(number=1, title="第一集"),
            )
            == "改写第一行\n改写第二行"
        )

        assert (
            await load_episode_planning_content(
                store,
                NovelEpisode(
                    number=1,
                    title="第一集",
                    beat_source_text="最终制作稿第一行\n最终制作稿第二行",
                ),
            )
            == "最终制作稿第一行\n最终制作稿第二行"
        )

        await store.save_adapted_content(1, "")

        assert await store.load_adapted_content(1) == ""
        assert await store.load_working_content(1) == "原文第一行\n原文第二行"
        assert (
            await load_episode_planning_content(
                store,
                NovelEpisode(number=1, title="第一集"),
            )
            == "原文第一行\n原文第二行"
        )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_save_adapted_content_requires_existing_episode(tmp_path) -> None:
    store = SQLiteStore(
        "admin/demo",
        output_dir=str(tmp_path / "output" / "admin" / "demo"),
        state_dir=str(tmp_path / "state" / "admin" / "demo"),
    )
    try:
        await store.initialize()
        with pytest.raises(ValueError, match="剧集 99 不存在"):
            await store.save_adapted_content(99, "missing")
    finally:
        await store.close()


class _RewriteRouteStore:
    def __init__(self):
        self.adapted_content = ""
        self.episode_updates: list[tuple[int, dict]] = []
        self.episode = NovelEpisode(number=1, title="第一集", raw_content="原文")

    async def load_episode_content(self, ep_num: int):
        return self.episode.raw_content if ep_num == self.episode.number else ""

    async def load_graph_state(self):
        return None

    def get_episode(self, ep_num: int):
        return self.episode if ep_num == self.episode.number else None

    def get_all_characters(self):
        return []

    async def save_adapted_content(self, ep_num: int, content: str) -> None:
        assert ep_num == self.episode.number
        self.adapted_content = content

    async def patch_episode(self, episode_number: int, **updates) -> None:
        # The real store offers both; the rewrite route takes the
        # column-level one so it cannot roll back planned menus.
        await self.update_episode(episode_number, **updates)

    async def update_episode(self, episode_number: int, **updates) -> None:
        self.episode_updates.append((episode_number, updates))
        for key, value in updates.items():
            setattr(self.episode, key, value)


class _UsageMeter:
    def __init__(self):
        self.reserved: list[dict] = []
        self.confirmed: list[tuple[str, dict]] = []
        self.refunded: list[tuple[str, dict]] = []
        self.interrupted: list[tuple[str, dict]] = []
        self.contexts: list[tuple[str, dict]] = []
        self.clear_count = 0

    async def reserve_feature_start_credits(self, **kwargs):
        self.reserved.append(kwargs)
        return {"id": "reservation-1", "cost": 6}

    async def settle_feature_credit_reservation(
        self, reservation_id: str, *, action: str, metadata=None
    ):
        target = self.confirmed if action == "confirm" else self.refunded
        target.append((reservation_id, metadata or {}))

    async def settle_cancelled_feature_credit_reservation(
        self, reservation_id: str, *, metadata=None
    ):
        self.interrupted.append((reservation_id, metadata or {}))

    def set_llm_usage_context(self, user_id: str, **kwargs):
        self.contexts.append((user_id, kwargs))

    def clear_llm_usage_context(self):
        self.clear_count += 1


@pytest.mark.asyncio
async def test_generate_rewrite_applies_output_to_beat_source_text(monkeypatch) -> None:
    from novelvideo.agents import content_rewriter
    from novelvideo.api.routes import content
    from novelvideo.api.schemas import RewriteGenerateRequest

    async def fake_rewrite_episode_content(*args, **kwargs):
        return "改写第一行\n改写第二行"

    monkeypatch.setattr(
        content_rewriter,
        "rewrite_episode_content",
        fake_rewrite_episode_content,
    )
    meter = _UsageMeter()
    monkeypatch.setattr(content, "get_usage_meter", lambda: meter)

    async def fake_resolve_project_scope(*args, **kwargs):
        return SimpleNamespace(
            ctx=SimpleNamespace(project_id="project-1", requester_user_id="user-1")
        )

    monkeypatch.setattr(content, "resolve_project_scope", fake_resolve_project_scope)

    store = _RewriteRouteStore()
    response = await content.generate_rewrite(
        project="demo",
        episode_num=1,
        body=RewriteGenerateRequest(),
        user={"username": "admin"},
        store=store,
    )

    assert response["ok"] is True
    assert store.adapted_content == "改写第一行\n改写第二行"
    assert store.episode.beat_source_text == "改写第一行\n改写第二行"
    assert store.episode_updates == [
        (1, {"beat_source_text": "改写第一行\n改写第二行"})
    ]
    assert meter.reserved[0]["feature_key"] == "mainline.content_rewrite"
    assert meter.reserved[0]["task_type"] == "content_rewrite"
    assert meter.reserved[0]["require_price_rule"] is True
    assert meter.reserved[0]["require_positive_cost"] is True
    assert meter.contexts[0][1]["billing_metadata"]["model_call_credit_policy"] == (
        "feature_included"
    )
    assert meter.confirmed[0][0] == "reservation-1"
    assert meter.refunded == []
    assert meter.clear_count == 1


@pytest.mark.asyncio
async def test_generate_rewrite_uses_evidence_settlement_on_failure(monkeypatch) -> None:
    from novelvideo.agents import content_rewriter
    from novelvideo.api.routes import content
    from novelvideo.api.schemas import RewriteGenerateRequest

    async def fail_rewrite_episode_content(*args, **kwargs):
        raise RuntimeError("rewrite failed")

    monkeypatch.setattr(
        content_rewriter,
        "rewrite_episode_content",
        fail_rewrite_episode_content,
    )
    meter = _UsageMeter()
    monkeypatch.setattr(content, "get_usage_meter", lambda: meter)

    async def fake_resolve_project_scope(*args, **kwargs):
        return SimpleNamespace(
            ctx=SimpleNamespace(project_id="project-1", requester_user_id="user-1")
        )

    monkeypatch.setattr(content, "resolve_project_scope", fake_resolve_project_scope)

    with pytest.raises(RuntimeError, match="rewrite failed"):
        await content.generate_rewrite(
            project="demo",
            episode_num=1,
            body=RewriteGenerateRequest(),
            user={"username": "admin"},
            store=_RewriteRouteStore(),
        )

    assert meter.confirmed == []
    assert meter.refunded == []
    assert meter.interrupted[0][0] == "reservation-1"
    assert meter.interrupted[0][1]["source"] == "sync_api"
    assert meter.clear_count == 1


@pytest.mark.asyncio
async def test_generate_rewrite_does_not_refund_success_when_confirm_is_pending(
    monkeypatch,
) -> None:
    from novelvideo.agents import content_rewriter
    from novelvideo.api.routes import content
    from novelvideo.api.schemas import RewriteGenerateRequest

    async def fake_rewrite_episode_content(*args, **kwargs):
        return "已成功改写"

    class ConfirmPendingMeter(_UsageMeter):
        async def settle_feature_credit_reservation(
            self, reservation_id: str, *, action: str, metadata=None
        ):
            if action == "confirm":
                raise RuntimeError("settlement unavailable")
            await super().settle_feature_credit_reservation(
                reservation_id,
                action=action,
                metadata=metadata,
            )

    monkeypatch.setattr(
        content_rewriter,
        "rewrite_episode_content",
        fake_rewrite_episode_content,
    )
    meter = ConfirmPendingMeter()
    monkeypatch.setattr(content, "get_usage_meter", lambda: meter)

    async def fake_resolve_project_scope(*args, **kwargs):
        return SimpleNamespace(
            ctx=SimpleNamespace(project_id="project-1", requester_user_id="user-1")
        )

    monkeypatch.setattr(content, "resolve_project_scope", fake_resolve_project_scope)

    response = await content.generate_rewrite(
        project="demo",
        episode_num=1,
        body=RewriteGenerateRequest(),
        user={"username": "admin"},
        store=_RewriteRouteStore(),
    )

    assert response["ok"] is True
    assert response["data"]["adapted_content"] == "已成功改写"
    assert meter.refunded == []


@pytest.mark.asyncio
async def test_content_rewriter_uses_newapi_text_model(monkeypatch) -> None:
    from novelvideo.agents import content_rewriter

    calls: dict[str, object] = {}

    class FakeAgent:
        def __init__(self, model, **kwargs):
            calls["model"] = model
            calls["kwargs"] = kwargs

        async def run(self, task: str):
            calls["task"] = task
            output_type = calls["kwargs"]["output_type"]
            return type(
                "FakeResult",
                (),
                {
                    "output": output_type(
                        lines=["第一行改写内容足够十四个字符。", "第二行改写内容同样十四个字符。"]
                    )
                },
            )()

    def fake_newapi_model(
        model_env: str, default_model: str, *, capability: str = "text.generate"
    ):
        calls["model_env"] = model_env
        calls["default_model"] = default_model
        calls["capability"] = capability
        return "newapi-model"

    def fake_newapi_settings():
        calls["structured_settings_called"] = True
        return {"openai_reasoning_effort": "none"}

    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    monkeypatch.setenv("NEWAPI_API_KEY", "newapi-token")
    monkeypatch.setattr(content_rewriter, "Agent", FakeAgent)
    monkeypatch.setattr(
        content_rewriter,
        "get_newapi_text_pydantic_model",
        fake_newapi_model,
        raising=False,
    )
    monkeypatch.setattr(
        content_rewriter,
        "get_newapi_structured_output_model_settings",
        fake_newapi_settings,
        raising=False,
    )

    rewritten = await content_rewriter.rewrite_episode_content(
        "原文第一段",
        episode_title="第一集",
        target_beats=2,
    )

    assert rewritten == "第一行改写内容足够十四个字符。\n第二行改写内容同样十四个字符。"
    assert calls["model"] == "newapi-model"
    assert calls["model_env"] == "CONTENT_REWRITER_MODEL"
    assert calls["default_model"] == "gpt-5.4-mini"
    assert calls["capability"] == "text.generate"
    assert calls["structured_settings_called"] is True


def test_content_rewriter_output_type_enforces_requested_limits() -> None:
    from novelvideo.agents.content_rewriter import _constrained_output_type

    from pydantic import ValidationError

    output_type = _constrained_output_type(6, 40, 70)
    valid_line = "这是一条满足四十字下限的改写文本，用于确认用户配置会成为真正的输出硬约束（含标点符号）。"
    assert 40 <= len(valid_line) <= 70

    output = output_type(lines=[valid_line] * 6)
    assert len(output.lines) == 6

    with pytest.raises(ValidationError):
        output_type(lines=[valid_line] * 5)

    with pytest.raises(ValidationError):
        output_type(lines=["字数不足"] * 6)


def test_rewrite_generate_request_validates_limits() -> None:
    from novelvideo.api.schemas import RewriteGenerateRequest

    from pydantic import ValidationError

    request = RewriteGenerateRequest(
        target_beats=6,
        beat_chars_min=40,
        beat_chars_max=70,
    )
    assert request.target_beats == 6

    with pytest.raises(ValidationError):
        RewriteGenerateRequest(beat_chars_min=40, beat_chars_max=20)


@pytest.mark.asyncio
async def test_content_rewriter_suggests_settings_from_story_density(monkeypatch) -> None:
    from novelvideo.agents import content_rewriter

    calls: dict[str, object] = {}

    class FakeAgent:
        def __init__(self, model, **kwargs):
            calls["kwargs"] = kwargs

        async def run(self, task: str):
            calls["task"] = task
            output_type = calls["kwargs"]["output_type"]
            return type(
                "FakeResult",
                (),
                {
                    "output": output_type(
                        target_beats=9,
                        beat_chars_min=18,
                        beat_chars_max=32,
                        rationale="原文虽长，但有效冲突集中在九个事件节点。",
                    )
                },
            )()

    monkeypatch.setattr(content_rewriter, "Agent", FakeAgent)
    monkeypatch.setattr(
        content_rewriter,
        "get_newapi_text_pydantic_model",
        lambda *args: "newapi-model",
    )
    monkeypatch.setattr(
        content_rewriter,
        "get_newapi_structured_output_model_settings",
        lambda: {},
    )

    suggestion = await content_rewriter.suggest_rewrite_settings(
        "大量重复铺垫之后，主角终于完成一次关键反击。",
        episode_title="第一集",
    )

    assert suggestion.target_beats == 9
    assert suggestion.beat_chars_min == 18
    assert suggestion.beat_chars_max == 32
    assert "不要按原文总字数机械换算" in calls["kwargs"]["system_prompt"]
    assert "有效剧情密度" in calls["task"]


@pytest.mark.asyncio
async def test_suggest_rewrite_settings_route_returns_ai_recommendation(monkeypatch) -> None:
    from novelvideo.agents import content_rewriter
    from novelvideo.api.routes import content
    from novelvideo.api.schemas import RewriteSettingsSuggestionRequest

    async def fake_suggest(*args, **kwargs):
        return content_rewriter.RewriteSettingsSuggestion(
            target_beats=8,
            beat_chars_min=16,
            beat_chars_max=28,
            rationale="去除重复心理后有八个有效事件节点。",
        )

    monkeypatch.setattr(content_rewriter, "suggest_rewrite_settings", fake_suggest)
    meter = _UsageMeter()
    monkeypatch.setattr(content, "get_usage_meter", lambda: meter)

    async def fake_resolve_project_scope(*args, **kwargs):
        return SimpleNamespace(
            ctx=SimpleNamespace(project_id="project-1", requester_user_id="user-1")
        )

    monkeypatch.setattr(content, "resolve_project_scope", fake_resolve_project_scope)

    response = await content.suggest_rewrite_settings(
        project="demo",
        episode_num=1,
        body=RewriteSettingsSuggestionRequest(),
        user={"username": "admin"},
        store=_RewriteRouteStore(),
    )

    assert response["ok"] is True
    assert response["data"]["target_beats"] == 8
    assert response["data"]["beat_chars_min"] == 16
    assert response["data"]["beat_chars_max"] == 28
    assert meter.reserved[0]["feature_key"] == "mainline.content_rewrite"
    assert meter.confirmed[0][0] == "reservation-1"
