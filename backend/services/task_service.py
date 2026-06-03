"""决策任务业务服务。"""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from ai.prompt_builder import build_agent_prompt, build_default_weight_config
from ai.scoring_core import calculate_weighted_ranking
from db.models import DecisionTask, TaskAgent, User
from schemas.task import (
    AgentConfigResponse,
    AgentOutputResponse,
    ConflictResultResponse,
    SimilarityResultResponse,
    TaskCreate,
    TaskStatusResponse,
    WeightedRankingItem,
)
from services.exceptions import ServiceError
from services.repositories.task_repository import (
    get_task_by_id,
    get_task_with_analysis,
)


class TaskService:
    """任务创建、状态查询与结果组装。"""

    @staticmethod
    def normalize_weight_config(weight_config: str | None) -> str:
        if weight_config is None:
            return build_default_weight_config()
        try:
            parsed = json.loads(weight_config)
        except json.JSONDecodeError as exc:
            raise ServiceError("权重配置格式错误，请提供合法的 JSON 字符串") from exc
        if not isinstance(parsed, dict):
            raise ServiceError("权重配置必须是 JSON 对象")
        total = sum(float(v) for v in parsed.values())
        if abs(total - 1.0) > 0.05:
            raise ServiceError(f"权重总和应为 1.0，当前为 {total}")
        return weight_config

    @staticmethod
    def validate_task_create(task_data: TaskCreate) -> None:
        if task_data.agent_count != len(task_data.agents):
            raise ServiceError(
                f"Agent 数量（{task_data.agent_count}）与配置列表长度"
                f"（{len(task_data.agents)}）不一致"
            )
        if task_data.agent_count < 2 or task_data.agent_count > 5:
            raise ServiceError(
                f"Agent 数量必须在 2~5 之间，当前为 {task_data.agent_count}"
            )

    @staticmethod
    def ensure_task_access(task: DecisionTask, user: User) -> None:
        if task.user_id != user.id and user.role != "admin":
            raise ServiceError("无权访问其他用户的任务", status_code=403)

    @staticmethod
    async def create_task(
        db: AsyncSession,
        user: User,
        task_data: TaskCreate,
    ) -> DecisionTask:
        TaskService.validate_task_create(task_data)
        weight_config = TaskService.normalize_weight_config(task_data.weight_config)

        new_task = DecisionTask(
            user_id=user.id,
            question=task_data.question,
            decision_mode=task_data.decision_mode,
            agent_count=task_data.agent_count,
            weight_config=weight_config,
            status="pending",
        )
        db.add(new_task)
        await db.flush()

        for agent_cfg in task_data.agents:
            final_prompt = build_agent_prompt(
                agent_name=agent_cfg.agent_name,
                role_description=agent_cfg.role_description,
                focus_area=agent_cfg.focus_area,
                tone=agent_cfg.tone,
                decision_mode=task_data.decision_mode,
                question=task_data.question,
            )
            db.add(
                TaskAgent(
                    task_id=new_task.id,
                    agent_name=agent_cfg.agent_name,
                    role_description=agent_cfg.role_description,
                    focus_area=agent_cfg.focus_area,
                    tone=agent_cfg.tone,
                    final_prompt=final_prompt,
                )
            )

        await db.commit()
        await db.refresh(new_task)
        return new_task

    @staticmethod
    async def get_status(
        db: AsyncSession,
        task_id: int,
        user: User,
    ) -> TaskStatusResponse:
        task = await get_task_by_id(db, task_id)
        if task is None:
            raise ServiceError(f"任务 {task_id} 不存在", status_code=404)
        TaskService.ensure_task_access(task, user)
        return TaskStatusResponse(
            task_id=task.id,
            status=task.status,
            error_message=task.error_message,
        )

    @staticmethod
    def build_result_payload(task: DecisionTask) -> dict:
        agent_name_map = {agent.id: agent.agent_name for agent in task.task_agents}

        output_responses = [
            AgentOutputResponse(
                id=output.id,
                task_id=output.task_id,
                task_agent_id=output.task_agent_id,
                agent_name=agent_name_map.get(output.task_agent_id, "未知"),
                output_text=output.output_text,
                score_json=output.score_json,
                created_at=output.created_at,
            )
            for output in task.agent_outputs
        ]

        similarity_responses = [
            SimilarityResultResponse.model_validate(s)
            for s in task.similarity_results
        ]
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

    @staticmethod
    async def get_result(
        db: AsyncSession,
        task_id: int,
        user: User,
    ) -> dict:
        task = await get_task_with_analysis(db, task_id)
        if task is None:
            raise ServiceError(f"任务 {task_id} 不存在", status_code=404)
        TaskService.ensure_task_access(task, user)
        if task.status in ("pending", "processing"):
            raise ServiceError(
                f"任务尚未处理完成，当前状态: {task.status}",
                status_code=400,
            )
        return TaskService.build_result_payload(task)

    @staticmethod
    async def get_completed_task_for_export(
        db: AsyncSession,
        task_id: int,
        user: User,
    ) -> DecisionTask:
        task = await get_task_with_analysis(db, task_id)
        if task is None:
            raise ServiceError("任务不存在", status_code=404)
        TaskService.ensure_task_access(task, user)
        if task.status != "completed":
            raise ServiceError("只能导出已完成的任务", status_code=400)
        return task
