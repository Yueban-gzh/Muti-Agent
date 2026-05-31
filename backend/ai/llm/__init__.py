"""LLM 推理层：local / api 统一入口。"""

from ai.llm.chat import llm_chat
from ai.llm.local_client import preload_local_model

__all__ = ["llm_chat", "preload_local_model"]
