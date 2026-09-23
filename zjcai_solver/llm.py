# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, List, Optional

from openai import OpenAI

# 题面中的 [图片N] 占位符与随后附上的图片按顺序一一对应，需要显式告诉模型
_IMAGE_HINT = "\n\n（上文中的 [图片1]、[图片2] …… 按顺序对应随后附上的图片。）"


class DeepSeekClient:
    """DeepSeek Chat API 的轻量封装，支持图片输入。

    图片只能出现在 user 消息中，放进 system/assistant 会被 API 拒绝（400）。
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-flash",
        reasoning_effort: str = "high",
    ):
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model or "deepseek-flash"
        self._reasoning_effort = (reasoning_effort or "").strip()

    def ask(
        self,
        system_prompt: str,
        user_prompt: str,
        images: Optional[List[str]] = None,
    ) -> str:
        """发送对话并返回 assistant 文本；images 为图片 data URI 列表。"""
        if images:
            content: Any = [{"type": "text", "text": user_prompt + _IMAGE_HINT}]
            content += [
                {"type": "image_url", "image_url": {"url": uri}} for uri in images
            ]
        else:
            # 无图片时保持纯字符串，省去多余的块结构
            content = user_prompt

        extra: Dict[str, Any] = {}
        if self._reasoning_effort:
            extra["reasoning_effort"] = self._reasoning_effort

        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            stream=False,
            **extra,
        )
        content_out = resp.choices[0].message.content
        return (content_out or "").strip()
