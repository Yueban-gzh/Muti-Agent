"""后台 AI 分析流水线入口。"""

from sqlalchemy import select

from ai.agent_core import process_task_background
from ai.orchestrators.finalize_pipeline import process_finalize_pipeline
from db.database import AsyncSessionLocal
from db.models import DecisionTask


async def run_task_pipeline(task_id: int) -> None:
    """按任务状态路由到收束流水线或旧版一次性流水线。"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(DecisionTask.status).where(DecisionTask.id == task_id)
        )
        status = result.scalar_one_or_none()

    if status == "finalizing":
        await process_finalize_pipeline(task_id)
    else:
        await process_task_background(task_id)
