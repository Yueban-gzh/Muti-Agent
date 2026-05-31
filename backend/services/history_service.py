"""历史记录业务服务。"""

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User
from services.repositories.task_repository import list_user_tasks


class HistoryService:
    @staticmethod
    async def list_user_history(db: AsyncSession, user: User) -> list[dict]:
        tasks = await list_user_tasks(db, user.id)
        return [
            {
                "id": task.id,
                "question": task.question,
                "decision_mode": task.decision_mode,
                "agent_count": task.agent_count,
                "status": task.status,
                "created_at": task.created_at.isoformat(),
            }
            for task in tasks
        ]
