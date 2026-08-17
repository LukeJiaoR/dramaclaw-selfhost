"""Provider-neutral AI voice design through the configured model gateway."""

from __future__ import annotations

import base64
from typing import Any

import httpx
from pydantic_ai import Agent

from novelvideo.config import get_newapi_runtime_credentials
from novelvideo.official_defaults import DEFAULT_VOICE_PROMPT_OPTIMIZER_MODEL


VOICE_DESIGN_MODEL = "DC-voice-design"
MAX_VOICE_DESCRIPTION_CHARS = 1000
MAX_PREVIEW_TEXT_CHARS = 500
MAX_AUDIO_BYTES = 20 * 1024 * 1024

VOICE_PROMPT_OPTIMIZER_SYSTEM_PROMPT = """你是有声剧声线设计师，负责把用户的简略描述改写成可直接交给语音设计模型的中文声线提示词。

要求：
1. 只描述可从声音听出的特征，包括年龄感、性别感、音高、音色、语速、咬字、情绪底色、表演方式和录音质感。
2. 保留用户明确提出的特征，不得擅自改变角色设定。
3. 结合角色资料补足有助于有声剧表演的细节，但不要写外貌、剧情、动作、模型参数或具体台词。
4. 使用自然、明确、无歧义的中文，控制在 80 至 180 个汉字左右，单段输出。
5. 只返回优化后的声线描述，不要标题、解释、引号、Markdown 或备选方案。
"""


def _clean_optimized_description(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()
    quote_pairs = {'"': '"', "'": "'", "“": "”", "‘": "’"}
    if len(text) >= 2 and quote_pairs.get(text[0]) == text[-1]:
        text = text[1:-1].strip()
    return text


async def optimize_voice_description(
    *,
    description: str,
    preview_text: str = "",
    subject_context: str,
) -> str:
    """Polish a voice-design prompt through the configured text gateway."""
    clean_description = str(description or "").strip()
    if not clean_description:
        raise ValueError("请先填写声线描述")
    if len(clean_description) > MAX_VOICE_DESCRIPTION_CHARS:
        raise ValueError(f"声线描述不能超过 {MAX_VOICE_DESCRIPTION_CHARS} 个字符")

    from novelvideo.config import get_newapi_text_pydantic_model

    model = get_newapi_text_pydantic_model(
        "VOICE_PROMPT_OPTIMIZER_MODEL",
        DEFAULT_VOICE_PROMPT_OPTIMIZER_MODEL,
        timeout_seconds_override=120.0,
    )
    agent = Agent(
        model,
        system_prompt=VOICE_PROMPT_OPTIMIZER_SYSTEM_PROMPT,
        output_type=str,
        name="Voice Prompt Optimizer",
    )
    task = (
        f"对象资料：\n{str(subject_context or '').strip()}\n\n"
        f"当前声线描述：\n{clean_description}"
    )
    clean_preview = str(preview_text or "").strip()
    if clean_preview:
        task += f"\n\n试听文本（仅用于判断表演语气，不要复述进结果）：\n{clean_preview[:MAX_PREVIEW_TEXT_CHARS]}"
    response = await agent.run(task)
    optimized = _clean_optimized_description(response.output)
    if not optimized:
        raise RuntimeError("文本模型未返回声线描述")
    if len(optimized) > MAX_VOICE_DESCRIPTION_CHARS:
        optimized = optimized[:MAX_VOICE_DESCRIPTION_CHARS].rstrip()
    return optimized


def _audio_from_json(payload: dict[str, Any]) -> bytes:
    audio = payload.get("audio") if isinstance(payload.get("audio"), dict) else {}
    encoded = str(
        payload.get("b64_json")
        or audio.get("data")
        or audio.get("b64_json")
        or ""
    ).strip()
    if not encoded:
        data = payload.get("data")
        if isinstance(data, list) and data and isinstance(data[0], dict):
            encoded = str(
                data[0].get("b64_json") or data[0].get("audio") or ""
            ).strip()
    if encoded.startswith("data:") and "," in encoded:
        encoded = encoded.split(",", 1)[1]
    if not encoded:
        raise RuntimeError("Voice design provider returned no audio data")
    try:
        return base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise RuntimeError("Voice design provider returned invalid audio data") from exc


async def generate_voice_design_audio(
    *,
    description: str,
    preview_text: str,
) -> bytes:
    clean_description = str(description or "").strip()
    clean_preview = str(preview_text or "").strip()
    if not clean_description:
        raise ValueError("请填写声线描述")
    if not clean_preview:
        raise ValueError("请填写试听文本")
    if len(clean_description) > MAX_VOICE_DESCRIPTION_CHARS:
        raise ValueError(f"声线描述不能超过 {MAX_VOICE_DESCRIPTION_CHARS} 个字符")
    if len(clean_preview) > MAX_PREVIEW_TEXT_CHARS:
        raise ValueError(f"试听文本不能超过 {MAX_PREVIEW_TEXT_CHARS} 个字符")

    api_key, base_url = get_newapi_runtime_credentials()
    endpoint = f"{str(base_url or '').rstrip('/')}/audio/speech"
    if not str(base_url or "").strip():
        raise RuntimeError("模型网关未配置")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = {
        "model": VOICE_DESIGN_MODEL,
        "input": clean_preview,
        "instructions": clean_description,
        "voice": "mimo_default",
        "response_format": "mp3",
    }
    async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as client:
        response = await client.post(endpoint, headers=headers, json=body)
    if response.status_code < 200 or response.status_code >= 300:
        detail = response.text[:1000]
        raise RuntimeError(
            f"声线生成失败（HTTP {response.status_code}）: {detail}"
        )
    content_type = str(response.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        try:
            content = _audio_from_json(response.json())
        except (TypeError, ValueError) as exc:
            raise RuntimeError("声线生成服务返回了无效 JSON") from exc
    else:
        content = response.content
    if not content:
        raise RuntimeError("声线生成服务返回了空音频")
    if len(content) > MAX_AUDIO_BYTES:
        raise RuntimeError("声线生成音频超过 20 MB 限制")
    return content
