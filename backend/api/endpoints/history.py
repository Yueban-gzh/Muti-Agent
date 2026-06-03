"""
历史记录与报告导出接口
---------------------
薄控制器：历史列表与报告下载，业务逻辑委托 services 层。
"""

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user
from api.http_utils import service_error_to_http
from db.database import get_db
from db.models import User
from services.exceptions import ServiceError
from services.history_service import HistoryService
from services.report_service import build_decision_report_markdown
from services.task_service import TaskService

router = APIRouter(prefix="/api/history", tags=["历史记录"])


@router.get(
    "/",
    summary="获取历史任务列表",
    description="返回当前登录用户的所有历史决策任务，按创建时间倒序排列。",
)
async def get_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    return await HistoryService.list_user_history(db, current_user)


@router.get(
    "/{task_id}/export",
    summary="导出决策报告（Markdown）",
    description="将指定任务的完整分析结果排版为 Markdown 格式，以 .md 文件下载。",
    response_class=PlainTextResponse,
)
async def export_report(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    try:
        task = await TaskService.get_completed_task_for_export(
            db, task_id, current_user
        )
    except ServiceError as exc:
        raise service_error_to_http(exc) from exc

    report_text = build_decision_report_markdown(task)
    safe_name = f"decision_report_{task.id}.md"

    return PlainTextResponse(
        content=report_text,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={safe_name}"},
    )
