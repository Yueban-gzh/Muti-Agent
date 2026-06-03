"""
决策任务接口模块
---------------
薄控制器：HTTP 参数校验与响应，业务逻辑委托 services 层。
"""

from fastapi import APIRouter, Depends, HTTPException, status

from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user
from api.http_utils import service_error_to_http
from db.database import get_db
from db.models import User
from schemas.task import TaskCreate, TaskResponse, TaskStatusResponse
from services.exceptions import ServiceError
from services.task_runner import TaskQueueFullError, get_task_runner
from services.task_service import TaskService

router = APIRouter(prefix="/api/tasks", tags=["决策任务"])


@router.post(
    "/create",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建决策任务",
    description="提交决策问题、Agent 配置和权重，系统将在后台异步处理完整的分析流水线。",
)
async def create_task(
    task_data: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        new_task = await TaskService.create_task(db, current_user, task_data)
    except ServiceError as exc:
        raise service_error_to_http(exc) from exc

    try:
        await get_task_runner().submit(new_task.id)
    except TaskQueueFullError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return {
        "task_id": new_task.id,
        "status": "pending",
        "message": "任务已提交，正在后台处理",
    }


@router.get(
    "/{task_id}/status",
    response_model=TaskStatusResponse,
    summary="查询任务状态",
)
async def get_task_status(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskStatusResponse:
    try:
        return await TaskService.get_status(db, task_id, current_user)
    except ServiceError as exc:
        raise service_error_to_http(exc) from exc


@router.get(
    "/{task_id}/result",
    summary="获取任务完整结果",
    description="获取任务详情及完整分析数据（Agent 配置/输出、相似度、冲突、综合建议）。",
)
async def get_task_result(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        return await TaskService.get_result(db, task_id, current_user)
    except ServiceError as exc:
        raise service_error_to_http(exc) from exc
