"""决策任务业务服务。"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai.prompt_builder import OUTPUT_FORMAT_INSTRUCTION, build_default_weight_config
from ai.prompts.debate_exchange import agent_display_name, stance_label
from ai.prompts.persona import build_finalize_system_prompt
from ai.scoring_core import calculate_weighted_ranking
from core.config import LEGACY_AUTO_FINALIZE, MAX_DISCUSSION_USER_TURNS
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
from services.agent_config_resolver import resolve_agent_config, validate_debate_stances
from services.discussion_service import DiscussionService
from services.exceptions import ServiceError
from services.log_constants import TASK_CREATE
from services.log_service import append_log
from services.repositories.task_repository import (
    get_task_by_id,
    get_task_with_analysis,
)


class TaskService:
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
            raise ServiceError("Agent 数量必须在 2~5 之间")

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

        use_legacy = task_data.legacy_auto_finalize
        if use_legacy is None:
            use_legacy = LEGACY_AUTO_FINALIZE

        if use_legacy:
            initial_status = "pending"
        elif task_data.start_discussion:
            initial_status = "discussing"
        else:
            initial_status = "pending"

        new_task = DecisionTask(
            user_id=user.id,
            question=task_data.question,
            decision_mode=task_data.decision_mode,
            agent_count=task_data.agent_count,
            weight_config=weight_config,
            status=initial_status,
            context_notes=(task_data.context_notes or "").strip() or None,
            discussion_turns=0,
        )
        db.add(new_task)
        await db.flush()

        resolved_agents: list[dict] = []
        used_tones: set = set()
        for idx, agent_cfg in enumerate(task_data.agents):
            resolved = await resolve_agent_config(
                db, agent_cfg, task_data.decision_mode, idx, used_tones
            )
            resolved_agents.append(resolved)

        if task_data.decision_mode == "debate":
            validate_debate_stances(resolved_agents)

        task_agents: list[TaskAgent] = []
        for idx, resolved in enumerate(resolved_agents):
            final_prompt = build_finalize_system_prompt(
                agent_name=resolved["agent_name"],
                role_description=resolved["role_description"],
                focus_area=resolved["focus_area"],
                tone=resolved["tone"],
                stance=resolved["stance"],
                extra_notes=resolved["extra_notes"],
                decision_mode=task_data.decision_mode,
                question=task_data.question,
                output_format_instruction=OUTPUT_FORMAT_INSTRUCTION,
            )
            agent = TaskAgent(
                task_id=new_task.id,
                agent_name=resolved["agent_name"],
                role_description=resolved["role_description"],
                focus_area=resolved["focus_area"],
                tone=resolved["tone"],
                stance=resolved["stance"],
                template_id=resolved["template_id"],
                extra_notes=resolved["extra_notes"],
                sort_order=idx,
                final_prompt=final_prompt,
            )
            db.add(agent)
            task_agents.append(agent)

        await db.commit()
        await db.refresh(new_task)

        if new_task.status == "discussing":
            agents_result = await db.execute(
                select(TaskAgent).where(TaskAgent.task_id == new_task.id)
            )
            agents = list(agents_result.scalars().all())
            await DiscussionService.ensure_welcome_message(db, new_task, agents)

        await append_log(
            TASK_CREATE,
            f"创建任务 #{new_task.id}，模式={new_task.decision_mode}，状态={new_task.status}",
            user_id=user.id,
        )

        new_task._legacy_auto_finalize = use_legacy  # type: ignore[attr-defined]
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
            decision_mode=task.decision_mode,
            discussion_turns=task.discussion_turns or 0,
            max_discussion_turns=MAX_DISCUSSION_USER_TURNS,
            can_finalize=task.status == "discussing",
            error_message=task.error_message,
            debate_exchange_rounds=getattr(task, "debate_exchange_rounds", 0) or 0,
        )

    @staticmethod
    def build_result_payload(task: DecisionTask, messages: list[dict] | None = None) -> dict:
        agent_name_map = {agent.id: agent.agent_name for agent in task.task_agents}

        output_responses = [
            AgentOutputResponse(
                id=output.id,
                task_id=output.task_id,
                task_agent_id=output.task_agent_id,
                agent_name=agent_name_map.get(output.task_agent_id, "未知"),
                output_text=output.output_text,
                score_json=output.score_json,
                phase=getattr(output, "phase", "final") or "final",
                round=getattr(output, "round", 1) or 1,
                created_at=output.created_at,
            )
            for output in task.agent_outputs
        ]

        similarity_responses = [
            SimilarityResultResponse.model_validate(s) for s in task.similarity_results
        ]
        conflict_responses = [
            ConflictResultResponse.model_validate(c) for c in task.conflict_results
        ]

        weighted_ranking = []
        if task.agent_outputs and task.status == "completed":
            weighted_ranking = calculate_weighted_ranking(
                task.agent_outputs,
                agent_name_map,
                task.weight_config,
            )
        ranking_responses = [
            WeightedRankingItem.model_validate(item) for item in weighted_ranking
        ]
        agent_responses = []
        for agent in task.task_agents:
            row = AgentConfigResponse.model_validate(agent).model_dump()
            row["stance_label"] = stance_label(agent.stance)
            row["agent_display_name"] = agent_display_name(
                agent.agent_name, agent.stance
            )
            agent_responses.append(row)

        return {
            "task_id": task.id,
            "question": task.question,
            "decision_mode": task.decision_mode,
            "agent_count": task.agent_count,
            "weight_config": task.weight_config,
            "status": task.status,
            "error_message": task.error_message,
            "final_summary": task.final_summary,
            "context_notes": task.context_notes,
            "discussion_summary": task.discussion_summary,
            "summary_method": task.summary_method,
            "created_at": task.created_at,
            "agents": agent_responses,
            "outputs": output_responses,
            "messages": messages or [],
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

        messages: list[dict] = []
        if task.status in ("discussing", "finalizing", "completed", "failed"):
            messages = await DiscussionService.list_messages(db, task, user)

        if task.status == "discussing":
            payload = TaskService.build_result_payload(task, messages)
            return payload

        if task.status == "finalizing":
            payload = TaskService.build_result_payload(task, messages)
            return payload

        if task.status in ("pending", "processing"):
            raise ServiceError(
                f"任务尚未完成，当前状态: {task.status}",
                status_code=400,
            )

        return TaskService.build_result_payload(task, messages)

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
