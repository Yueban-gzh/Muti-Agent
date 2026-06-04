"""收束任务：状态更新并入队。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import DecisionTask, User
from services.discussion_service import DiscussionService
from services.exceptions import ServiceError
from services.log_constants import TASK_FINALIZE_START
from services.log_service import append_log
from services.task_runner import get_task_runner, TaskQueueFullError


class FinalizeService:
    @staticmethod
    async def finalize_task(db: AsyncSession, task: DecisionTask, user: User) -> DecisionTask:
        from services.task_service import TaskService

        TaskService.ensure_task_access(task, user)
        if task.status != "discussing":
            raise ServiceError(
                f"仅 discussing 状态可收束，当前: {task.status}",
                status_code=400,
            )

        from sqlalchemy import select
        from db.models import TaskAgent

        agents_result = await db.execute(
            select(TaskAgent).where(TaskAgent.task_id == task.id)
        )
        agents = list(agents_result.scalars().all())
        await DiscussionService.ensure_welcome_message(db, task, agents)

        task.status = "finalizing"
        task.error_message = None
        await db.commit()
        await db.refresh(task)

        await append_log(
            TASK_FINALIZE_START,
            f"任务 {task.id} 开始收束（讨论轮次 {task.discussion_turns}）",
            user_id=user.id,
        )

        try:
            await get_task_runner().submit_finalize(task.id)
        except TaskQueueFullError as e:
            task.status = "discussing"
            await db.commit()
            raise ServiceError(str(e), status_code=503) from e

        return task
