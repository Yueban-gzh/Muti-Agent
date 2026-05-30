"""
管理员后台接口
-------------
提供管理员专属的系统管理功能，包括用户管理、全站任务查看、
数据统计看板、模板 CRUD 和操作日志查询。

所有接口挂载在 /api/admin 路由前缀下，需要管理员权限。
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_admin
from db.database import get_db
from db.models import (
    User,
    DecisionTask,
    TaskAgent,
    AgentOutput,
    UserFeedback,
    AgentTemplate,
    OperationLog,
)
from schemas.admin import (
    AdminUserResponse,
    AdminTaskResponse,
    AdminStatsResponse,
    LogResponse,
)
from schemas.template import (
    TemplateCreate,
    TemplateUpdate,
    TemplateResponse,
)

# ============================================================================
# 路由初始化
# ============================================================================

router = APIRouter(prefix="/api/admin", tags=["管理员后台"])


# ============================================================================
# GET /api/admin/users — 用户列表
# ============================================================================


@router.get(
    "/users",
    response_model=list[AdminUserResponse],
    summary="获取用户列表",
    description="返回系统中所有注册用户的列表。需要管理员权限。",
)
async def get_all_users(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> list[AdminUserResponse]:
    """管理员查看所有用户"""
    result = await db.execute(
        select(User).order_by(User.id)
    )
    users = result.scalars().all()
    return [AdminUserResponse.model_validate(u) for u in users]


# ============================================================================
# GET /api/admin/tasks — 全站任务列表
# ============================================================================


@router.get(
    "/tasks",
    summary="获取全站任务列表",
    description="返回系统中所有决策任务的列表。需要管理员权限。",
)
async def get_all_tasks(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200, description="返回条数上限"),
    offset: int = Query(default=0, ge=0, description="偏移量"),
) -> list[dict]:
    """管理员查看全站所有任务"""
    result = await db.execute(
        select(DecisionTask, User.username)
        .join(User, DecisionTask.user_id == User.id)
        .order_by(desc(DecisionTask.created_at))
        .offset(offset)
        .limit(limit)
    )
    rows = result.all()

    return [
        {
            "id": task.id,
            "user_id": task.user_id,
            "username": username,
            "question": task.question,
            "decision_mode": task.decision_mode,
            "agent_count": task.agent_count,
            "status": task.status,
            "created_at": task.created_at,
        }
        for task, username in rows
    ]


# ============================================================================
# GET /api/admin/stats — 全局数据看板
# ============================================================================


@router.get(
    "/stats",
    response_model=AdminStatsResponse,
    summary="全局数据统计",
    description="返回系统全局统计数据看板。需要管理员权限。",
)
async def get_admin_stats(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminStatsResponse:
    """
    管理员全局数据看板

    统计内容:
        - 用户总数、管理员数量
        - 任务总数、完成数、失败数
        - 反馈采纳比例
        - 模板数量
    """
    # --- 用户统计 ---
    total_users_result = await db.execute(select(func.count(User.id)))
    total_users = total_users_result.scalar() or 0

    admin_result = await db.execute(
        select(func.count(User.id)).where(User.role == "admin")
    )
    total_admin_users = admin_result.scalar() or 0

    # --- 任务统计 ---
    total_tasks_result = await db.execute(select(func.count(DecisionTask.id)))
    total_tasks = total_tasks_result.scalar() or 0

    completed_result = await db.execute(
        select(func.count(DecisionTask.id)).where(DecisionTask.status == "completed")
    )
    completed_tasks = completed_result.scalar() or 0

    failed_result = await db.execute(
        select(func.count(DecisionTask.id)).where(DecisionTask.status == "failed")
    )
    failed_tasks = failed_result.scalar() or 0

    pending_result = await db.execute(
        select(func.count(DecisionTask.id)).where(
            DecisionTask.status.in_(["pending", "processing"])
        )
    )
    pending_tasks = pending_result.scalar() or 0

    # --- 反馈统计 ---
    total_fb_result = await db.execute(select(func.count(UserFeedback.id)))
    total_feedback = total_fb_result.scalar() or 0

    agent_fb_result = await db.execute(
        select(func.count(UserFeedback.id)).where(UserFeedback.chosen_type == "agent")
    )
    agent_adoption_count = agent_fb_result.scalar() or 0

    summary_fb_result = await db.execute(
        select(func.count(UserFeedback.id)).where(UserFeedback.chosen_type == "summary")
    )
    summary_adoption_count = summary_fb_result.scalar() or 0

    none_fb_result = await db.execute(
        select(func.count(UserFeedback.id)).where(UserFeedback.chosen_type == "none")
    )
    none_adoption_count = none_fb_result.scalar() or 0

    # --- 模板统计 ---
    total_tpl_result = await db.execute(select(func.count(AgentTemplate.id)))
    total_templates = total_tpl_result.scalar() or 0

    active_tpl_result = await db.execute(
        select(func.count(AgentTemplate.id)).where(AgentTemplate.is_active == 1)
    )
    active_templates = active_tpl_result.scalar() or 0

    return AdminStatsResponse(
        total_users=total_users,
        total_admin_users=total_admin_users,
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        failed_tasks=failed_tasks,
        pending_tasks=pending_tasks,
        total_feedback=total_feedback,
        agent_adoption_count=agent_adoption_count,
        summary_adoption_count=summary_adoption_count,
        none_adoption_count=none_adoption_count,
        total_templates=total_templates,
        active_templates=active_templates,
    )


# ============================================================================
# POST /api/admin/templates — 创建模板
# ============================================================================


@router.post(
    "/templates",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建 Agent 模板",
    description="在模板库中新增一个 Agent 预设模板。需要管理员权限。",
)
async def create_template(
    template_data: TemplateCreate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> TemplateResponse:
    """管理员创建 Agent 模板"""
    # 检查名称是否重复
    existing = await db.execute(
        select(AgentTemplate).where(AgentTemplate.name == template_data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"模板名称 '{template_data.name}' 已存在",
        )

    new_template = AgentTemplate(
        name=template_data.name,
        role_description=template_data.role_description,
        focus_area=template_data.focus_area,
        tone=template_data.tone,
        is_active=template_data.is_active,
    )
    db.add(new_template)
    await db.commit()
    await db.refresh(new_template)

    return TemplateResponse.model_validate(new_template)


# ============================================================================
# PUT /api/admin/templates/{template_id} — 更新模板
# ============================================================================


@router.put(
    "/templates/{template_id}",
    response_model=TemplateResponse,
    summary="更新 Agent 模板",
    description="修改指定 Agent 模板的配置信息。需要管理员权限。",
)
async def update_template(
    template_id: int,
    template_data: TemplateUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> TemplateResponse:
    """管理员更新 Agent 模板"""
    result = await db.execute(
        select(AgentTemplate).where(AgentTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()

    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模板不存在")

    # 只更新传入的非空字段
    update_data = template_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(template, field, value)

    await db.commit()
    await db.refresh(template)

    return TemplateResponse.model_validate(template)


# ============================================================================
# DELETE /api/admin/templates/{template_id} — 删除模板
# ============================================================================


@router.delete(
    "/templates/{template_id}",
    summary="删除 Agent 模板",
    description="从模板库中删除指定模板。需要管理员权限。",
)
async def delete_template(
    template_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """管理员删除 Agent 模板"""
    result = await db.execute(
        select(AgentTemplate).where(AgentTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()

    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模板不存在")

    await db.delete(template)
    await db.commit()

    return {"message": f"模板 '{template.name}' 已删除", "template_id": template_id}


# ============================================================================
# GET /api/admin/logs — 操作日志查询
# ============================================================================


@router.get(
    "/logs",
    response_model=list[LogResponse],
    summary="查看操作日志",
    description="查询系统操作日志。需要管理员权限。",
)
async def get_operation_logs(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500, description="返回条数上限"),
    event_type: str = Query(default=None, description="按事件类型筛选"),
) -> list[LogResponse]:
    """管理员查看系统操作日志"""
    query = select(OperationLog).order_by(desc(OperationLog.created_at))

    if event_type:
        query = query.where(OperationLog.event_type == event_type)

    query = query.limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()

    return [LogResponse.model_validate(l) for l in logs]
