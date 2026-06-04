"""任务相关数据库查询（Repository 层）。"""

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import DecisionTask


async def get_task_by_id(db: AsyncSession, task_id: int) -> DecisionTask | None:
    result = await db.execute(
        select(DecisionTask).where(DecisionTask.id == task_id)
    )
    return result.scalar_one_or_none()


async def get_task_with_analysis(db: AsyncSession, task_id: int) -> DecisionTask | None:
    """加载任务及分析结果关联数据。"""
    result = await db.execute(
        select(DecisionTask)
        .where(DecisionTask.id == task_id)
        .options(
            selectinload(DecisionTask.task_agents),
            selectinload(DecisionTask.agent_outputs),
            selectinload(DecisionTask.similarity_results),
            selectinload(DecisionTask.conflict_results),
        )
    )
    return result.scalar_one_or_none()


async def list_user_tasks(db: AsyncSession, user_id: int) -> list[DecisionTask]:
    result = await db.execute(
        select(DecisionTask)
        .where(DecisionTask.user_id == user_id)
        .order_by(desc(DecisionTask.created_at))
    )
    return list(result.scalars().all())
