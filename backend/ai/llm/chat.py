"""统一 LLM 入口：按 LLM_BACKEND 路由到本地或 API。"""

from __future__ import annotations

from typing import Optional

from core.config import LLM_BACKEND, LOCAL_MAX_NEW_TOKENS

from ai.llm.api_client import api_chat_completion
from ai.llm.local_client import chat_completion as local_chat_completion
from services.llm_scheduler import LLMSlot


async def llm_chat(
    system_prompt: str,
    user_message: str,
    *,
    temperature: Optional[float] = None,
    max_new_tokens: Optional[int] = None,
    task_id: Optional[int] = None,
    label: str = "",
) -> dict:
    """
    统一聊天接口。

    返回:
        {"success": bool, "text": str | None, "error": str | None}
    """
    async with LLMSlot(task_id=task_id, label=label):
        if LLM_BACKEND == "local":
            return await local_chat_completion(
                system_prompt,
                user_message,
                temperature=temperature,
                max_new_tokens=max_new_tokens,
            )

        max_tokens = (
            max_new_tokens if max_new_tokens is not None else LOCAL_MAX_NEW_TOKENS
        )
        temp = 0.7 if temperature is None else temperature
        return await api_chat_completion(
            system_prompt,
            user_message,
            temperature=temp,
            max_tokens=max_tokens,
        )
