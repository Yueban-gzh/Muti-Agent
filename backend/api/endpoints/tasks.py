"""
决策任务接口模块
"""

from fastapi import APIRouter, Depends, Query

from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user
from api.http_utils import service_error_to_http
from core.config import LEGACY_AUTO_FINALIZE
from db.database import get_db
from db.models import User
from schemas.discussion import (
    DebateAgentExchangeResponse,
    DebateRosterItem,
    DiscussionMessageCreate,
    DiscussionMessageBatchResponse,
)
from schemas.task import TaskCreate, TaskResponse, TaskStatusResponse
from services.discussion_service import DiscussionService
from services.exceptions import ServiceError
from services.finalize_service import FinalizeService
from services.task_runner import TaskQueueFullError, get_task_runner
from services.task_service import TaskService
from services.repositories.task_repository import get_task_by_id

router = APIRouter(prefix="/api/tasks", tags=["决策任务"])


@router.post(
    "/create",
    response_model=TaskResponse,
    status_code=201,
    summary="创建决策任务",
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

    use_legacy = getattr(new_task, "_legacy_auto_finalize", LEGACY_AUTO_FINALIZE)
    if use_legacy:
        try:
            new_task.status = "pending"
            await db.commit()
            await db.refresh(new_task)
            await get_task_runner().submit(new_task.id)
        except TaskQueueFullError as exc:
            raise service_error_to_http(
                ServiceError(str(exc), status_code=503)
            ) from exc
        return {
            "task_id": new_task.id,
            "status": "pending",
            "message": "任务已提交，正在后台处理（兼容模式）",
        }

    return {
        "task_id": new_task.id,
        "status": new_task.status,
        "message": "任务已创建，请进入讨论室交流后生成正式分析",
    }


@router.get(
    "/{task_id}/debate-roster",
    response_model=list[DebateRosterItem],
    summary="辩论辩手席位（含立场标签）",
)
async def get_debate_roster(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    task = await get_task_by_id(db, task_id)
    if task is None:
        raise service_error_to_http(ServiceError("任务不存在", status_code=404))
    try:
        return await DiscussionService.get_debate_roster(db, task, current_user)
    except ServiceError as exc:
        raise service_error_to_http(exc) from exc


@router.post(
    "/{task_id}/debate/agent-exchange",
    response_model=DebateAgentExchangeResponse,
    summary="辩手自主交锋一轮（用户不发言）",
)
async def debate_agent_exchange(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    task = await get_task_by_id(db, task_id)
    if task is None:
        raise service_error_to_http(ServiceError("任务不存在", status_code=404))
    try:
        return await DiscussionService.run_agent_exchange(db, task, current_user)
    except ServiceError as exc:
        raise service_error_to_http(exc) from exc


@router.post(
    "/{task_id}/messages",
    response_model=DiscussionMessageBatchResponse,
    status_code=201,
    summary="发送讨论消息",
)
async def post_discussion_message(
    task_id: int,
    body: DiscussionMessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    task = await get_task_by_id(db, task_id)
    if task is None:
        raise service_error_to_http(ServiceError("任务不存在", status_code=404))
    try:
        return await DiscussionService.post_message(db, task, current_user, body)
    except ServiceError as exc:
        raise service_error_to_http(exc) from exc


@router.get(
    "/{task_id}/messages",
    summary="获取讨论消息列表",
)
async def list_discussion_messages(
    task_id: int,
    after_seq: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    task = await get_task_by_id(db, task_id)
    if task is None:
        raise service_error_to_http(ServiceError("任务不存在", status_code=404))
    try:
        return await DiscussionService.list_messages(
            db, task, current_user, after_seq=after_seq, limit=limit
        )
    except ServiceError as exc:
        raise service_error_to_http(exc) from exc


@router.post(
    "/{task_id}/finalize",
    response_model=TaskStatusResponse,
    summary="结束讨论并生成正式分析",
)
async def finalize_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskStatusResponse:
    task = await get_task_by_id(db, task_id)
    if task is None:
        raise service_error_to_http(ServiceError("任务不存在", status_code=404))
    try:
        task = await FinalizeService.finalize_task(db, task, current_user)
    except ServiceError as exc:
        raise service_error_to_http(exc) from exc
    return await TaskService.get_status(db, task_id, current_user)


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
    summary="获取任务结果（含讨论记录）",
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
