"""
本地 Qwen 模型推理客户端
-----------------------
全局单例加载模型，对外提供 async chat_completion()。
"""

from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import Optional

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from core.config import (
    LOCAL_MAX_CONCURRENT,
    LOCAL_MAX_NEW_TOKENS,
    LOCAL_MODEL_PATH,
    LOCAL_TEMPERATURE,
)

logger = logging.getLogger("local_client")

_model: Optional[AutoModelForCausalLM] = None
_tokenizer: Optional[AutoTokenizer] = None
_load_lock = threading.Lock()
_semaphore: Optional[asyncio.Semaphore] = None


class LocalLLMError(Exception):
    """本地模型加载或推理失败。"""


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(LOCAL_MAX_CONCURRENT)
    return _semaphore


def preload_local_model() -> None:
    """启动时预加载模型（FastAPI lifespan 调用）。"""
    _ensure_loaded()


def _ensure_loaded() -> None:
    global _model, _tokenizer

    if _model is not None and _tokenizer is not None:
        return

    with _load_lock:
        if _model is not None and _tokenizer is not None:
            return

        model_path = Path(LOCAL_MODEL_PATH)
        if not model_path.exists():
            raise LocalLLMError(
                f"本地模型目录不存在: {model_path}。"
                "请先运行 python scripts/test_local_llm.py 确认模型已下载。"
            )

        logger.info("正在加载本地模型: %s", model_path)
        _tokenizer = AutoTokenizer.from_pretrained(
            str(model_path), trust_remote_code=True
        )
        _model = AutoModelForCausalLM.from_pretrained(
            str(model_path),
            torch_dtype=torch.float16,
            device_map="auto",
            trust_remote_code=True,
        )
        logger.info(
            "本地模型加载完成 (cuda=%s)",
            torch.cuda.is_available(),
        )


def _sync_generate(
    system_prompt: str,
    user_message: str,
    temperature: float,
    max_new_tokens: int,
) -> str:
    _ensure_loaded()
    assert _tokenizer is not None and _model is not None

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    prompt = _tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = _tokenizer(prompt, return_tensors="pt").to(_model.device)

    gen_kwargs: dict = {
        "max_new_tokens": max_new_tokens,
        "do_sample": temperature > 0,
        "top_p": 0.9,
    }
    if temperature > 0:
        gen_kwargs["temperature"] = temperature

    with torch.no_grad():
        output_ids = _model.generate(**inputs, **gen_kwargs)

    new_tokens = output_ids[0][inputs["input_ids"].shape[1] :]
    return _tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


async def chat_completion(
    system_prompt: str,
    user_message: str,
    *,
    temperature: Optional[float] = None,
    max_new_tokens: Optional[int] = None,
) -> dict:
    """
    异步调用本地模型生成回复。

    返回:
        {"success": bool, "text": str | None, "error": str | None}
    """
    temp = LOCAL_TEMPERATURE if temperature is None else temperature
    max_tokens = LOCAL_MAX_NEW_TOKENS if max_new_tokens is None else max_new_tokens

    sem = _get_semaphore()
    async with sem:
        try:
            text = await asyncio.to_thread(
                _sync_generate,
                system_prompt,
                user_message,
                temp,
                max_tokens,
            )
            logger.info("本地生成完成，长度 %d 字符", len(text))
            return {"success": True, "text": text, "error": None}
        except LocalLLMError as e:
            logger.error("本地模型错误: %s", e)
            return {"success": False, "text": None, "error": str(e)}
        except Exception as e:
            logger.exception("本地模型推理异常")
            return {"success": False, "text": None, "error": str(e)}
