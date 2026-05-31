"""
AI 核心模块
----------
负责与大模型通信，实现多 Agent 的异步并发调用。
包含后台任务的主处理函数，串联完整的分析流水线：
  1. 并发 Agent 调用 → 2. 相似度 → 3. 冲突检测 → 4. 加权排名 → 5. 综合建议
"""

import asyncio
import json
import logging
import re
import traceback
from typing import Optional

from sqlalchemy import select

from ai.conflict_core import detect_conflicts
from ai.llm.chat import llm_chat
from ai.scoring_core import calculate_weighted_ranking
from ai.similarity_core import calculate_similarities
from ai.summary_core import generate_final_summary
from db.database import AsyncSessionLocal
from db.models import (
    DecisionTask,
    TaskAgent,
    AgentOutput,
    SimilarityResult,
    ConflictResult,
)

# ============================================================================
# 日志配置
# ============================================================================

logger = logging.getLogger("agent_core")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s"
    ))
    logger.addHandler(handler)


# ============================================================================
# 评分 JSON 解析工具
# ============================================================================


def _extract_score_json(output_text: str) -> Optional[str]:
    """从 Agent 输出文本中提取六维评分 JSON。"""
    if not output_text:
        return None

    # 策略 1: 匹配 ```json ... ``` 代码块
    json_block_pattern = r'```json\s*([\s\S]*?)\s*```'
    match = re.search(json_block_pattern, output_text)
    if match:
        json_str = match.group(1).strip()
        try:
            parsed = json.loads(json_str)
            expected_keys = {"benefit", "cost", "risk", "tech", "exec", "long_term"}
            if expected_keys.issubset(set(parsed.keys())):
                return json.dumps(parsed, ensure_ascii=False)
        except (json.JSONDecodeError, AttributeError):
            pass

    # 策略 2: 匹配任意 {...} JSON 对象
    loose_pattern = r'\{[^{}]*"benefit"[^{}]*\}'
    match = re.search(loose_pattern, output_text)
    if match:
        json_str = match.group(0).strip()
        try:
            parsed = json.loads(json_str)
            expected_keys = {"benefit", "cost", "risk", "tech", "exec", "long_term"}
            if expected_keys.issubset(set(parsed.keys())):
                return json.dumps(parsed, ensure_ascii=False)
        except (json.JSONDecodeError, AttributeError):
            pass

    logger.warning("未能从输出中提取有效的评分 JSON")
    return None


# ============================================================================
# 单个 Agent 的大模型调用
# ============================================================================


async def generate_single_agent_response(
    system_prompt: str,
    user_question: str,
) -> dict:
    """
    调用大模型，使用给定的 System Prompt 生成单个 Agent 的回答。
    后端由 os.env 中 LLM_BACKEND 决定（local / api）。
    """
    user_message = f"请分析以下决策问题：\n{user_question}"
    result = await llm_chat(
        system_prompt,
        user_message,
        temperature=0.7,
        max_new_tokens=2048,
    )

    if result["success"] and result["text"]:
        output_text = result["text"]
        score_json = _extract_score_json(output_text)
        logger.info("Agent 生成成功，回复长度: %d 字符", len(output_text))
        return {
            "success": True,
            "output_text": output_text,
            "score_json": score_json,
            "error": None,
        }

    return {
        "success": False,
        "output_text": None,
        "score_json": None,
        "error": result.get("error") or "未知错误",
    }


# ============================================================================
# 后台任务主处理函数（第三阶段：完整流水线）
# ============================================================================


async def process_task_background(task_id: int) -> None:
    """
    后台任务主处理函数 — 完整分析流水线。

    流水线步骤:
        1. 查询任务及 Agent 配置
        2. asyncio.gather 并发调用所有 Agent
        3. 保存 AgentOutput 到数据库
        4. 相似度计算 → 保存 SimilarityResult
        5. 冲突检测 → 保存 ConflictResult
        6. 综合建议生成 → 更新 DecisionTask.final_summary
        7. 更新任务状态为 completed / failed
    """
    logger.info(f"[任务 {task_id}] 后台处理流水线启动...")

    async with AsyncSessionLocal() as db:
        try:
            # =============================================================
            # 步骤 1: 查询任务及 Agent 配置
            # =============================================================
            result = await db.execute(
                select(DecisionTask).where(DecisionTask.id == task_id)
            )
            task = result.scalar_one_or_none()

            if task is None:
                logger.error(f"[任务 {task_id}] 任务不存在")
                return

            agents_result = await db.execute(
                select(TaskAgent).where(TaskAgent.task_id == task_id)
            )
            task_agents = agents_result.scalars().all()

            if not task_agents:
                logger.error(f"[任务 {task_id}] 没有找到 Agent 配置")
                task.status = "failed"
                task.error_message = "没有找到 Agent 配置"
                await db.commit()
                return

            # =============================================================
            # 步骤 2: 更新状态 → processing
            # =============================================================
            task.status = "processing"
            await db.commit()
            logger.info(f"[任务 {task_id}] → processing ({len(task_agents)} 个 Agent)")

            # =============================================================
            # 步骤 3: 并发调用所有 Agent
            # =============================================================
            async def call_agent_safe(agent: TaskAgent) -> dict:
                try:
                    logger.info(f"[任务 {task_id}] 调用: {agent.agent_name}")
                    result_data = await generate_single_agent_response(
                        system_prompt=agent.final_prompt,
                        user_question=task.question,
                    )
                    result_data["agent"] = agent
                    logger.info(
                        f"[任务 {task_id}] {agent.agent_name}: "
                        f"{'成功' if result_data['success'] else '失败'}"
                    )
                    return result_data
                except Exception as e:
                    logger.error(f"[任务 {task_id}] {agent.agent_name} 异常: {traceback.format_exc()}")
                    return {
                        "success": False, "output_text": None,
                        "score_json": None,
                        "error": f"未捕获异常: {str(e)}", "agent": agent,
                    }

            agent_results: list[dict] = await asyncio.gather(
                *[call_agent_safe(agent) for agent in task_agents],
            )

            # =============================================================
            # 步骤 4: 保存 AgentOutput
            # =============================================================
            success_count = 0
            fail_count = 0

            for result_data in agent_results:
                agent = result_data.get("agent")
                if agent is None:
                    continue

                output_record = AgentOutput(
                    task_id=task_id,
                    task_agent_id=agent.id,
                    output_text=result_data.get("output_text"),
                    score_json=result_data.get("score_json"),
                )

                if not result_data.get("success"):
                    error_info = result_data.get("error", "未知错误")
                    output_record.output_text = (
                        f"[该 Agent 调用失败]\n错误信息: {error_info}\n\n"
                        + (output_record.output_text or "")
                    )
                    fail_count += 1
                else:
                    success_count += 1

                db.add(output_record)

            await db.commit()
            logger.info(f"[任务 {task_id}] Agent 完成: 成功 {success_count}/{len(agent_results)}")

            # =============================================================
            # 步骤 5: 检查是否有成功的结果（全部失败则提前终止）
            # =============================================================
            if fail_count == len(agent_results):
                task.status = "failed"
                task.error_message = "所有 Agent 调用均失败，请检查 LLM 配置或模型路径"
                await db.commit()
                logger.error(f"[任务 {task_id}] 全部 Agent 失败")
                return

            # ---- 重新查询 AgentOutput（确保获取到完整的 ORM 对象） ----
            outputs_result = await db.execute(
                select(AgentOutput).where(AgentOutput.task_id == task_id)
            )
            saved_outputs = outputs_result.scalars().all()

            # 构建 agent_name 映射
            agent_name_map = {agent.id: agent.agent_name for agent in task_agents}

            # =============================================================
            # 步骤 6: 相似度计算 + 写入数据库
            # =============================================================
            logger.info(f"[任务 {task_id}] 开始相似度计算...")
            try:
                sim_results = calculate_similarities(saved_outputs, agent_name_map)
                for sr in sim_results:
                    db.add(SimilarityResult(
                        task_id=task_id,
                        agent_id_1=sr["agent_id_1"],
                        agent_id_2=sr["agent_id_2"],
                        similarity=sr["similarity"],
                        explanation=sr["explanation"],
                    ))
                await db.commit()
                logger.info(f"[任务 {task_id}] 相似度结果已保存: {len(sim_results)} 条")
            except Exception as e:
                logger.error(f"[任务 {task_id}] 相似度计算异常: {traceback.format_exc()}")
                sim_results = []

            # =============================================================
            # 步骤 7: 冲突检测 + 写入数据库
            # =============================================================
            logger.info(f"[任务 {task_id}] 开始冲突检测...")
            try:
                conflict_results = detect_conflicts(saved_outputs, agent_name_map)
                for cr in conflict_results:
                    db.add(ConflictResult(
                        task_id=task_id,
                        dimension=cr["dimension"],
                        max_score=cr["max_score"],
                        min_score=cr["min_score"],
                        conflict_level=cr["conflict_level"],
                        explanation=cr["explanation"],
                    ))
                await db.commit()
                logger.info(f"[任务 {task_id}] 冲突结果已保存: {len(conflict_results)} 条")
            except Exception as e:
                logger.error(f"[任务 {task_id}] 冲突检测异常: {traceback.format_exc()}")
                conflict_results = []

            # =============================================================
            # 步骤 8: 加权评分排名
            # =============================================================
            logger.info(f"[任务 {task_id}] 开始加权评分排名...")
            try:
                weighted_ranking = calculate_weighted_ranking(
                    saved_outputs,
                    agent_name_map,
                    task.weight_config,
                )
                logger.info(
                    f"[任务 {task_id}] 加权排名完成: "
                    f"{sum(1 for r in weighted_ranking if r['score_available'])} 个有效评分"
                )
            except Exception as e:
                logger.error(f"[任务 {task_id}] 加权排名异常: {traceback.format_exc()}")
                weighted_ranking = []

            # =============================================================
            # 步骤 9: 综合建议生成 + 更新 DecisionTask
            # =============================================================
            logger.info(f"[任务 {task_id}] 开始生成综合建议...")
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
                )

                if summary_result["success"] and summary_result["summary_text"]:
                    task.final_summary = summary_result["summary_text"]
                    logger.info(f"[任务 {task_id}] 综合建议已生成")
                else:
                    fallback = (
                        "综合建议生成失败："
                        + (summary_result.get("error") or "未知错误")
                        + "\n\n请参考各专家独立分析意见。"
                    )
                    task.final_summary = fallback
                    logger.warning(f"[任务 {task_id}] 综合建议生成失败，使用降级文本")
            except Exception as e:
                logger.error(f"[任务 {task_id}] 综合建议异常: {traceback.format_exc()}")
                task.final_summary = f"综合建议生成过程中发生异常: {str(e)[:500]}"

            # =============================================================
            # 步骤 10: 标记任务完成
            # =============================================================
            task.status = "completed"
            if fail_count > 0:
                task.error_message = f"部分 Agent 调用失败（{fail_count}/{len(agent_results)}）"
            await db.commit()
            logger.info(f"[任务 {task_id}] → completed ✓")

        except Exception as e:
            # ---- 全局异常：尝试标记失败 ----
            logger.error(f"[任务 {task_id}] 流水线异常: {traceback.format_exc()}")
            try:
                result = await db.execute(
                    select(DecisionTask).where(DecisionTask.id == task_id)
                )
                task = result.scalar_one_or_none()
                if task:
                    task.status = "failed"
                    task.error_message = f"系统异常: {str(e)[:500]}"
                    await db.commit()
            except Exception:
                logger.error(f"[任务 {task_id}] 无法更新失败状态")

    logger.info(f"[任务 {task_id}] 后台流水线结束")
