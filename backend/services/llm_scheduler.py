"""全局 LLM 并发槽位调度。"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional

from core.config import LLM_MAX_CONCURRENT

logger = logging.getLogger("llm_scheduler")

_semaphore: Optional[asyncio.Semaphore] = None
_active: int = 0
_total_acquired: int = 0


def get_llm_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(LLM_MAX_CONCURRENT)
    return _semaphore


@dataclass
class LLMSchedulerStats:
    max_concurrent: int = LLM_MAX_CONCURRENT
    active: int = 0
    available_slots: int = LLM_MAX_CONCURRENT
    total_acquired: int = 0


def get_llm_stats() -> LLMSchedulerStats:
    sem = get_llm_semaphore()
    available = getattr(sem, "_value", 0)
    return LLMSchedulerStats(
        active=_active,
        available_slots=max(0, available),
        total_acquired=_total_acquired,
    )


class LLMSlot:
    """全局 LLM 槽位上下文管理器。"""

    def __init__(
        self,
        *,
        task_id: Optional[int] = None,
        label: str = "",
    ) -> None:
        self.task_id = task_id
        self.label = label
        self.wait_ms: int = 0

    async def __aenter__(self) -> "LLMSlot":
        global _active, _total_acquired
        t0 = time.monotonic()
        await get_llm_semaphore().acquire()
        self.wait_ms = int((time.monotonic() - t0) * 1000)
        _active += 1
        _total_acquired += 1
        if self.wait_ms > 500:
            logger.info(
                "LLM 槽位 acquired task=%s label=%s wait=%dms active=%d/%d",
                self.task_id,
                self.label,
                self.wait_ms,
                _active,
                LLM_MAX_CONCURRENT,
            )
        return self

    async def __aexit__(self, *exc) -> None:
        global _active
        _active = max(0, _active - 1)
        get_llm_semaphore().release()
