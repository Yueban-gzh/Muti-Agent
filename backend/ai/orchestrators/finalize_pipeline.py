"""收束期流水线：纪要 → 各 Agent 正式报告 → 相似度 / 冲突 / 综合建议。"""

from __future__ import annotations

import asyncio
import logging
import traceback
from typing import Optional

from sqlalchemy import delete, select

from ai.agent_core import _extract_score_json, generate_single_agent_response
from ai.conflict_core import detect_conflicts
from ai.discussion_summary import build_discussion_summary_llm
from ai.prompt_builder import OUTPUT_FORMAT_INSTRUCTION
from ai.prompts.persona import build_finalize_system_prompt
from ai.scoring_core import calculate_weighted_ranking
from ai.similarity_core import calculate_similarities
from ai.summary_core import generate_final_summary
from db.database import AsyncSessionLocal
from db.models import (
    AgentOutput,
    ConflictResult,
    DecisionTask,
    DiscussionMessage,
    SimilarityResult,
    TaskAgent,
)
from services.log_constants import (
    AGENT_ALL_FAILED,
    TASK_COMPLETED,
    TASK_FAILED,
    TASK_PROCESSING,
)
from services.log_service import append_log

logger = logging.getLogger("finalize_pipeline")


async def _generate_finalize_agent(
    agent: TaskAgent,
    task: DecisionTask,
    summary: str,
) -> dict:
    system = build_finalize_system_prompt(
        agent_name=agent.agent_name,
        role_description=agent.role_description,
        focus_area=agent.focus_area,
        tone=agent.tone,
        stance=agent.stance,
        extra_notes=agent.extra_notes,
        decision_mode=task.decision_mode,
        question=task.question,
        output_format_instruction=OUTPUT_FORMAT_INSTRUCTION,
    )
    user_message = (
        f"以下是本次决策讨论的纪要（约 800 字）：\n\n{summary}\n\n"
        "请基于该纪要和你的角色立场，输出正式决策分析报告（含六维评分 JSON）。"
    )
    result = await generate_single_agent_response(
        system,
        user_message,
        task_id=task.id,
        agent_name=agent.agent_name,
    )
    result["agent"] = agent
    return result


async def process_finalize_pipeline(task_id: int) -> None:
    logger.info("[任务 %s] 收束流水线启动", task_id)
    task_user_id: Optional[int] = None

    async with AsyncSessionLocal() as db:
        try:
            task = await db.get(DecisionTask, task_id)
            if not task:
                return
            task_user_id = task.user_id

            agents_result = await db.execute(
                select(TaskAgent).where(TaskAgent.task_id == task_id).order_by(TaskAgent.sort_order)
            )
            task_agents = list(agents_result.scalars().all())
            if not task_agents:
                task.status = "failed"
                task.error_message = "未找到 Agent 配置"
                await db.commit()
                return

            msg_result = await db.execute(
                select(DiscussionMessage)
                .where(DiscussionMessage.task_id == task_id)
                .order_by(DiscussionMessage.seq)
            )
            messages = list(msg_result.scalars().all())
            agents_by_id = {a.id: a for a in task_agents}

            if not task.discussion_summary:
                summary, method = await build_discussion_summary_llm(
                    task, messages, agents_by_id, task_id=task_id
                )
                task.discussion_summary = summary
                task.summary_method = method
                await db.commit()

            summary = task.discussion_summary or ""

            await db.execute(delete(AgentOutput).where(AgentOutput.task_id == task_id))
            await db.execute(delete(SimilarityResult).where(SimilarityResult.task_id == task_id))
            await db.execute(delete(ConflictResult).where(ConflictResult.task_id == task_id))
            await db.commit()

            await append_log(
                TASK_PROCESSING,
                f"任务 {task_id} 收束期：生成正式报告（{len(task_agents)} 个 Agent）",
                user_id=task_user_id,
            )

            async def call_safe(agent: TaskAgent) -> dict:
                try:
                    return await _generate_finalize_agent(agent, task, summary)
                except Exception:
                    logger.error(
                        "[任务 %s] %s 收束异常: %s",
                        task_id,
                        agent.agent_name,
                        traceback.format_exc(),
                    )
                    return {
                        "success": False,
                        "output_text": None,
                        "score_json": None,
                        "error": "未捕获异常",
                        "agent": agent,
                    }

            agent_results = await asyncio.gather(
                *[call_safe(a) for a in task_agents]
            )

            success_count = 0
            fail_count = 0
            for result_data in agent_results:
                agent = result_data.get("agent")
                if not agent:
                    continue
                record = AgentOutput(
                    task_id=task_id,
                    task_agent_id=agent.id,
                    output_text=result_data.get("output_text"),
                    score_json=result_data.get("score_json"),
                    phase="final",
                    round=1,
                )
                if not result_data.get("success"):
                    record.output_text = (
                        f"[该 Agent 收束调用失败]\n{result_data.get('error', '')}\n\n"
                        + (record.output_text or "")
                    )
                    fail_count += 1
                else:
                    success_count += 1
                db.add(record)

            await db.commit()

            if fail_count == len(agent_results):
                task.status = "failed"
                task.error_message = "收束期所有 Agent 调用均失败"
                await db.commit()
                await append_log(AGENT_ALL_FAILED, f"任务 {task_id} 收束全部失败", user_id=task_user_id)
                return

            outputs_result = await db.execute(
                select(AgentOutput).where(AgentOutput.task_id == task_id)
            )
            saved_outputs = list(outputs_result.scalars().all())
            agent_name_map = {a.id: a.agent_name for a in task_agents}

            sim_results = []
            try:
                sim_results = await asyncio.to_thread(
                    calculate_similarities, saved_outputs, agent_name_map
                )
                for sr in sim_results:
                    db.add(
                        SimilarityResult(
                            task_id=task_id,
                            agent_id_1=sr["agent_id_1"],
                            agent_id_2=sr["agent_id_2"],
                            similarity=sr["similarity"],
                            explanation=sr["explanation"],
                        )
                    )
                await db.commit()
            except Exception:
                logger.error("[任务 %s] 相似度异常: %s", task_id, traceback.format_exc())

            conflict_results = []
            try:
                conflict_results = detect_conflicts(saved_outputs, agent_name_map)
                for cr in conflict_results:
                    db.add(
                        ConflictResult(
                            task_id=task_id,
                            dimension=cr["dimension"],
                            max_score=cr["max_score"],
                            min_score=cr["min_score"],
                            conflict_level=cr["conflict_level"],
                            explanation=cr["explanation"],
                        )
                    )
                await db.commit()
            except Exception:
                logger.error("[任务 %s] 冲突检测异常: %s", task_id, traceback.format_exc())

            weighted_ranking = []
            try:
                weighted_ranking = calculate_weighted_ranking(
                    saved_outputs, agent_name_map, task.weight_config
                )
            except Exception:
                logger.error("[任务 %s] 加权排名异常: %s", task_id, traceback.format_exc())

            try:
                summary_result = await generate_final_summary(
                    question=task.question,
                    decision_mode=task.decision_mode,
                    outputs=saved_outputs,
                    similarities=sim_results,
                    conflicts=conflict_results,
                    weight_config=task.weight_config,
                    agent_name_map=agent_name_map,
                    weighted_ranking=weighted_ranking,
                    task_id=task_id,
                    discussion_summary=summary,
                )
                if summary_result.get("success") and summary_result.get("summary_text"):
                    task.final_summary = summary_result["summary_text"]
                else:
                    task.final_summary = (
                        "综合建议生成失败，请参考各专家正式报告及讨论纪要。"
                    )
            except Exception:
                task.final_summary = "综合建议生成异常，请参考各专家正式报告。"
                logger.error("[任务 %s] 综合建议异常: %s", task_id, traceback.format_exc())

            from datetime import datetime, timezone

            task.status = "completed"
            task.finalized_at = datetime.now(timezone.utc)
            if fail_count > 0:
                task.error_message = f"部分 Agent 收束失败（{fail_count}/{len(agent_results)}）"
            await db.commit()

            await append_log(
                TASK_COMPLETED,
                f"任务 {task_id} 收束完成",
                user_id=task_user_id,
            )

        except Exception as e:
            logger.error("[任务 %s] 收束流水线异常: %s", task_id, traceback.format_exc())
            try:
                task = await db.get(DecisionTask, task_id)
                if task:
                    task.status = "failed"
                    task.error_message = f"收束异常: {str(e)[:500]}"
                    await db.commit()
            except Exception:
                pass
            await append_log(
                TASK_FAILED,
                f"任务 {task_id} 收束异常: {str(e)[:500]}",
                user_id=task_user_id,
            )
