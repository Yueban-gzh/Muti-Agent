"""决策任务后台调度器（替换 FastAPI BackgroundTasks）。"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select

from core.config import MAX_CONCURRENT_PIPELINES, TASK_QUEUE_MAX_DEPTH
from db.database import AsyncSessionLocal
from db.models import DecisionTask
from services.pipeline_service import run_task_pipeline

logger = logging.getLogger("task_runner")

_runner: Optional["TaskRunner"] = None


class TaskQueueFullError(Exception):
    """任务队列已满。"""


@dataclass
class TaskRunnerStats:
    queue_depth: int = 0
    pipeline_active: int = 0
    pipeline_max: int = MAX_CONCURRENT_PIPELINES
    worker_running: bool = False


class TaskRunner:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[int] = asyncio.Queue()
        self._pipe_sem = asyncio.Semaphore(MAX_CONCURRENT_PIPELINES)
        self._worker_task: Optional[asyncio.Task] = None
        self._shutdown = False
        self._pipeline_active = 0

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    def stats(self) -> TaskRunnerStats:
        return TaskRunnerStats(
            queue_depth=self.queue_depth,
            pipeline_active=self._pipeline_active,
            worker_running=(
                self._worker_task is not None and not self._worker_task.done()
            ),
        )

    async def start(self) -> None:
        if self._worker_task is None or self._worker_task.done():
            self._shutdown = False
            self._worker_task = asyncio.create_task(self._worker_loop())
            logger.info(
                "TaskRunner 已启动 pipeline_max=%d", MAX_CONCURRENT_PIPELINES
            )

    async def stop(self, *, drain_timeout: float = 30.0) -> None:
        self._shutdown = True
        if self._worker_task:
            try:
                await asyncio.wait_for(self._worker_task, timeout=drain_timeout)
            except asyncio.TimeoutError:
                self._worker_task.cancel()
        logger.info("TaskRunner 已停止")

    async def submit(self, task_id: int) -> None:
        """旧版：创建后自动跑一次性流水线（LEGACY_AUTO_FINALIZE）。"""
        await self._enqueue(task_id)

    async def submit_finalize(self, task_id: int) -> None:
        """收束期流水线入队。"""
        await self._enqueue(task_id)

    async def _enqueue(self, task_id: int) -> None:
        if TASK_QUEUE_MAX_DEPTH > 0 and self.queue_depth >= TASK_QUEUE_MAX_DEPTH:
            raise TaskQueueFullError(
                f"任务队列已满（{TASK_QUEUE_MAX_DEPTH}），请稍后重试"
            )
        await self._queue.put(task_id)
        logger.info("任务 %d 已入队 queue_depth=%d", task_id, self.queue_depth)

    async def recover_stale_tasks(self) -> int:
        """启动时恢复 processing / finalizing 中断任务。"""
        recovered = 0
        async with AsyncSessionLocal() as db:
            proc = await db.execute(
                select(DecisionTask.id).where(DecisionTask.status == "processing")
            )
            proc_ids = list(proc.scalars().all())
            fin = await db.execute(
                select(DecisionTask.id).where(DecisionTask.status == "finalizing")
            )
            fin_ids = list(fin.scalars().all())

        for task_id in proc_ids:
            async with AsyncSessionLocal() as db:
                task = await db.get(DecisionTask, task_id)
                if task and task.status == "processing":
                    task.status = "pending"
                    task.error_message = None
                    await db.commit()
            await self._enqueue(task_id)
            recovered += 1

        for task_id in fin_ids:
            await self._enqueue(task_id)
            recovered += 1

        if recovered:
            logger.info("已恢复 %d 个中断任务", recovered)
        return recovered

    async def _worker_loop(self) -> None:
        while not self._shutdown:
            try:
                task_id = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            asyncio.create_task(self._run_pipeline(task_id))

    async def _run_pipeline(self, task_id: int) -> None:
        async with self._pipe_sem:
            self._pipeline_active += 1
            try:
                await run_task_pipeline(task_id)
            except Exception:
                logger.exception("任务 %d 流水线异常", task_id)
            finally:
                self._pipeline_active -= 1
                self._queue.task_done()


def init_task_runner() -> TaskRunner:
    global _runner
    _runner = TaskRunner()
    return _runner


def get_task_runner() -> TaskRunner:
    if _runner is None:
        raise RuntimeError(
            "TaskRunner 未初始化，请在 main.py lifespan 中调用 init_task_runner()"
        )
    return _runner
