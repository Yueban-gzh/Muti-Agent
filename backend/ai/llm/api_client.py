"""DeepSeek API 调用（LLM_BACKEND=api 时使用）。"""

from __future__ import annotations

import asyncio
import logging
import traceback
from typing import Optional

import httpx

from core.config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MAX_RETRIES,
    DEEPSEEK_MODEL,
    DEEPSEEK_TIMEOUT,
)

logger = logging.getLogger("api_client")


async def api_chat_completion(
    system_prompt: str,
    user_message: str,
    *,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> dict:
    """返回 {"success": bool, "text": str | None, "error": str | None}"""
    if not DEEPSEEK_API_KEY:
        return {
            "success": False,
            "text": None,
            "error": "未配置 DEEPSEEK_API_KEY，请在 os.env 中设置或改用 LLM_BACKEND=local",
        }

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    api_url = f"{DEEPSEEK_BASE_URL.rstrip('/')}/chat/completions"
    last_error: Optional[str] = None

    for attempt in range(1 + DEEPSEEK_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=DEEPSEEK_TIMEOUT, trust_env=False) as client:
                logger.info("调用 LLM API %s（第 %d 次）...", api_url, attempt + 1)
                response = await client.post(api_url, json=payload, headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    text = data["choices"][0]["message"]["content"]
                    return {"success": True, "text": text, "error": None}

                error_detail = response.text
                last_error = f"HTTP {response.status_code}: {error_detail[:500]}"
                logger.warning("LLM API 非 200: %s", last_error[:300])
                if 400 <= response.status_code < 500:
                    break

        except httpx.TimeoutException:
            last_error = f"请求超时（{DEEPSEEK_TIMEOUT}秒）"
        except httpx.ConnectError as e:
            last_error = f"连接失败: {e}"
        except Exception as e:
            last_error = f"未知异常: {e}"
            logger.error("API 调用异常: %s", traceback.format_exc())

        if attempt < DEEPSEEK_MAX_RETRIES:
            await asyncio.sleep(2 ** attempt)

    return {"success": False, "text": None, "error": last_error or "未知错误"}
