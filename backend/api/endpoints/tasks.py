"""
决策任务接口模块
---------------
提供决策任务的创建、状态轮询和结果获取的 RESTful API。
所有接口挂载在 /api/tasks 路由前缀下，需要用户登录。
第三阶段更新：结果接口增加相似度、冲突和综合建议数据。
"""

import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai.agent_core import process_task_background
from ai.prompt_builder import build_agent_prompt, build_default_weight_config
from ai.scoring_core import calculate_weighted_ranking
from api.dependencies import get_current_user
from db.database import get_db
from db.models import User, DecisionTask
from schemas.task import (
    TaskCreate,
    TaskResponse,
    TaskStatusResponse,
    AgentConfigResponse,
    AgentOutputResponse,
    SimilarityResultResponse,
    ConflictResultResponse,
    WeightedRankingItem,
)

# ============================================================================
# 路由初始化
# ============================================================================

router = APIRouter(prefix="/api/tasks", tags=["决策任务"])


# ============================================================================
# POST /api/tasks/create — 创建决策任务
# ============================================================================


@router.post(
    "/create",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建决策任务",
    description="提交决策问题、Agent 配置和权重，系统将在后台异步处理完整的分析流水线。",
)
async def create_task(
    task_data: TaskCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """创建决策任务接口"""
    # --- 校验 ---
    if task_data.agent_count != len(task_data.agents):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Agent 数量（{task_data.agent_count}）与配置列表长度（{len(task_data.agents)}）不一致",
        )
    if task_data.agent_count < 2 or task_data.agent_count > 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Agent 数量必须在 2~5 之间，当前为 {task_data.agent_count}",
        )

    # --- 处理权重 ---
    weight_config = task_data.weight_config
    if weight_config is None:
        weight_config = build_default_weight_config()
    else:
        try:
            parsed = json.loads(weight_config)
            total = sum(parsed.values())
            if abs(total - 1.0) > 0.05:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"权重总和应为 1.0，当前为 {total}",
                )
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="权重配置格式错误，请提供合法的 JSON 字符串",
            )

    # --- 创建 DecisionTask ---
    new_task = DecisionTask(
        user_id=current_user.id,
        question=task_data.question,
        decision_mode=task_data.decision_mode,
        agent_count=task_data.agent_count,
        weight_config=weight_config,
        status="pending",
    )
    db.add(new_task)
    await db.flush()

    # --- 创建 TaskAgent 记录 ---
    for agent_cfg in task_data.agents:
        final_prompt = build_agent_prompt(
            agent_name=agent_cfg.agent_name,
            role_description=agent_cfg.role_description,
            focus_area=agent_cfg.focus_area,
            tone=agent_cfg.tone,
            decision_mode=task_data.decision_mode,
            question=task_data.question,
        )
        db.add(TaskAgent(
            task_id=new_task.id,
            agent_name=agent_cfg.agent_name,
            role_description=agent_cfg.role_description,
            focus_area=agent_cfg.focus_area,
            tone=agent_cfg.tone,
            final_prompt=final_prompt,
        ))

    await db.commit()

    # --- 加入后台处理流水线 ---
    background_tasks.add_task(process_task_background, task_id=new_task.id)

    return {
        "task_id": new_task.id,
        "status": "pending",
        "message": "任务已提交，正在后台处理",
    }


# ============================================================================
# GET /api/tasks/{task_id}/status — 查询任务状态
# ============================================================================


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
    """查询任务处理状态"""
    result = await db.execute(select(DecisionTask).where(DecisionTask.id == task_id))
    task = result.scalar_one_or_none()

    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"任务 {task_id} 不存在")
    if task.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问其他用户的任务")

    return TaskStatusResponse(
        task_id=task.id,
        status=task.status,
        error_message=task.error_message,
    )


# ============================================================================
# GET /api/tasks/{task_id}/result — 获取任务完整结果
# ============================================================================


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
    """
    获取任务的完整分析结果

    返回:
        dict: 包含任务信息、Agent 配置/输出、相似度、冲突和综合建议
    """
    # 查询任务及其所有关联数据
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
    task = result.scalar_one_or_none()

    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"任务 {task_id} 不存在")
    if task.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问其他用户的任务")
    if task.status in ("pending", "processing"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"任务尚未处理完成，当前状态: {task.status}",
        )

    # 构建 agent_name 映射
    agent_name_map = {agent.id: agent.agent_name for agent in task.task_agents}

    # --- 构建输出列表 ---
    output_responses = []
    for output in task.agent_outputs:
        output_responses.append(AgentOutputResponse(
            id=output.id,
            task_id=output.task_id,
            task_agent_id=output.task_agent_id,
            agent_name=agent_name_map.get(output.task_agent_id, "未知"),
            output_text=output.output_text,
            score_json=output.score_json,
            created_at=output.created_at,
        ))

    # --- 构建相似度列表 ---
    similarity_responses = [
        SimilarityResultResponse.model_validate(s) for s in task.similarity_results
    ]

    # --- 构建冲突列表 ---
    conflict_responses = [
        ConflictResultResponse.model_validate(c) for c in task.conflict_results
    ]

    weighted_ranking = calculate_weighted_ranking(
        task.agent_outputs,
        agent_name_map,
        task.weight_config,
    )
    ranking_responses = [
        WeightedRankingItem.model_validate(item) for item in weighted_ranking
    ]

    # --- 构建 Agent 配置列表 ---
    agent_responses = [
        AgentConfigResponse.model_validate(agent) for agent in task.task_agents
    ]

    return {
        "task_id": task.id,
        "question": task.question,
        "decision_mode": task.decision_mode,
        "agent_count": task.agent_count,
        "weight_config": task.weight_config,
        "status": task.status,
        "error_message": task.error_message,
        "final_summary": task.final_summary,
        "created_at": task.created_at,
        "agents": agent_responses,
        "outputs": output_responses,
        "similarities": similarity_responses,
        "conflicts": conflict_responses,
        "weighted_ranking": ranking_responses,
    }
