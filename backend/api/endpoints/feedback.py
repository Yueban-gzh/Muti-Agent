"""
用户反馈接口模块
---------------
提供用户提交决策采纳反馈的 API，用于收集偏好数据。
所有接口挂载在 /api/feedback 路由前缀下，需要用户登录。
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user, get_current_admin
from db.database import get_db
from db.models import User, DecisionTask, UserFeedback
from schemas.feedback import FeedbackCreate, FeedbackResponse, FeedbackStatistics

# ============================================================================
# 路由初始化
# ============================================================================

router = APIRouter(prefix="/api/feedback", tags=["用户反馈"])


# ============================================================================
# POST /api/feedback/vote — 提交反馈（采纳投票）
# ============================================================================


@router.post(
    "/vote",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="提交决策反馈",
    description="用户选择采纳某个 Agent 或综合建议，系统保存偏好数据。",
)
async def submit_feedback(
    feedback_data: FeedbackCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FeedbackResponse:
    """
    提交用户反馈（采纳投票）

    处理流程:
        1. 校验任务是否存在且属于当前用户
        2. 校验任务是否已完成
        3. 校验 chosen_type 对应的 chosen_agent_id 是否合法
        4. 创建 UserFeedback 记录并返回

    参数:
        feedback_data: 反馈数据（task_id, chosen_type, chosen_agent_id, comment）
        current_user: 当前登录用户
        db: 异步数据库会话

    返回:
        FeedbackResponse: 保存后的反馈记录

    异常:
        404: 任务不存在
        403: 无权操作
        400: 参数非法
    """
    # --- 校验任务存在且属于当前用户 ---
    result = await db.execute(
        select(DecisionTask).where(DecisionTask.id == feedback_data.task_id)
    )
    task = result.scalar_one_or_none()

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务 {feedback_data.task_id} 不存在",
        )

    if task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权对此任务提交反馈",
        )

    # --- 校验任务已完成 ---
    if task.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"只能对已完成的任务提交反馈，当前状态: {task.status}",
        )

    # --- 校验 chosen_type 与 chosen_agent_id 的一致性 ---
    if feedback_data.chosen_type == "agent":
        if feedback_data.chosen_agent_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="采纳类型为 'agent' 时必须提供 chosen_agent_id",
            )
        # 验证该 agent 确实属于该任务
        from db.models import TaskAgent
        agent_result = await db.execute(
            select(TaskAgent).where(
                TaskAgent.id == feedback_data.chosen_agent_id,
                TaskAgent.task_id == feedback_data.task_id,
            )
        )
        if agent_result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Agent {feedback_data.chosen_agent_id} 不属于任务 {feedback_data.task_id}",
            )

    # --- 检查是否已提交过反馈（一个任务只允许一次反馈） ---
    existing = await db.execute(
        select(UserFeedback).where(
            UserFeedback.task_id == feedback_data.task_id,
            UserFeedback.user_id == current_user.id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="已对该任务提交过反馈，不可重复提交",
        )

    # --- 创建反馈记录 ---
    feedback = UserFeedback(
        task_id=feedback_data.task_id,
        user_id=current_user.id,
        chosen_type=feedback_data.chosen_type,
        chosen_agent_id=feedback_data.chosen_agent_id,
        comment=feedback_data.comment,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)

    return FeedbackResponse.model_validate(feedback)


# ============================================================================
# GET /api/feedback/stats — 管理员查看反馈统计
# ============================================================================


@router.get(
    "/stats",
    response_model=FeedbackStatistics,
    summary="查看反馈统计（管理员）",
    description="管理员查看所有用户的反馈采纳统计数据。",
)
async def get_feedback_stats(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> FeedbackStatistics:
    """
    查询反馈统计数据（仅管理员可访问）

    返回:
        FeedbackStatistics: 各类采纳次数的统计汇总
    """
    # 总反馈数
    total_result = await db.execute(select(func.count(UserFeedback.id)))
    total = total_result.scalar() or 0

    # 采纳 Agent 次数
    agent_result = await db.execute(
        select(func.count(UserFeedback.id)).where(UserFeedback.chosen_type == "agent")
    )
    agent_count = agent_result.scalar() or 0

    # 采纳综合建议次数
    summary_result = await db.execute(
        select(func.count(UserFeedback.id)).where(UserFeedback.chosen_type == "summary")
    )
    summary_count = summary_result.scalar() or 0

    # 暂不采纳次数
    none_result = await db.execute(
        select(func.count(UserFeedback.id)).where(UserFeedback.chosen_type == "none")
    )
    none_count = none_result.scalar() or 0

    return FeedbackStatistics(
        total_feedback_count=total,
        agent_adoption_count=agent_count,
        summary_adoption_count=summary_count,
        none_count=none_count,
    )
