"""
综合建议生成模块
---------------
将多个 Agent 的分析结果、相似度检测和冲突检测结果
拼接为一个大型 Prompt，再次调用大模型生成最终的综合建议。
"""

import logging
from typing import Optional

from ai.llm.chat import llm_chat
from ai.scoring_core import format_ranking_for_summary

logger = logging.getLogger("summary_core")

# ============================================================================
# 综合建议生成 Prompt 模板
# ============================================================================

SUMMARY_SYSTEM_PROMPT = """你是一位资深的决策分析顾问。你的任务是基于多个领域专家的分析意见，生成一份全面、客观的综合建议报告。

请严格按照以下格式输出你的综合建议：

---

## 1. 总体判断
（用 3~5 句话对该决策问题给出总体评价，明确指出值得推进还是需要谨慎）

## 2. 主要支持理由
（列出 3~5 条支持推进该方案的主要理由，从不同维度综合归纳）

## 3. 主要风险
（列出 3~5 条需要关注的主要风险，特别关注各专家之间存在分歧的风险点）

## 4. 分歧点说明
（说明专家之间在哪些方面存在明显意见分歧，分歧的原因可能是什么）

## 5. 推荐行动方案
（给出分阶段的、可执行的具体行动建议，包括试点计划、里程碑和决策节点）

## 6. 备选方案
（如果当前方案不可行或风险过高，提供 1~2 个备选方向）

## 7. 最终建议
（用 1~2 句话给出你最核心的建议）"""


# ============================================================================
# 综合建议生成函数
# ============================================================================


async def generate_final_summary(
    question: str,
    decision_mode: str,
    outputs: list,
    similarities: list[dict],
    conflicts: list[dict],
    weight_config: Optional[str] = None,
    agent_name_map: Optional[dict[int, str]] = None,
    weighted_ranking: Optional[list[dict]] = None,
    task_id: Optional[int] = None,
) -> dict:
    """
    调用大模型生成最终综合建议。

    将 Agent 输出、相似度结果、冲突结果拼接为 User Message，
    使用 System Prompt 要求大模型按固定格式输出结构化的综合建议。

    参数:
        question: 用户提出的决策问题
        decision_mode: 决策模式
        outputs: AgentOutput ORM 对象列表
        similarities: 相似度结果列表（dict 格式）
        conflicts: 冲突结果列表（dict 格式）
        weight_config: 用户权重配置 JSON
        agent_name_map: {agent_id: agent_name} 映射

    返回:
        dict: {"success": bool, "summary_text": str | None, "error": str | None}
    """
    if agent_name_map is None:
        agent_name_map = {}

    # =========================================================================
    # 第 1 步：构建 User Message — 汇总所有分析结果
    # =========================================================================
    user_message_parts = [
        f"【原始决策问题】\n{question}\n",
        f"【决策模式】{decision_mode}",
    ]

    if weight_config:
        user_message_parts.append(f"【用户权重配置】\n{weight_config}")

    # --- 汇总各 Agent 的输出 ---
    user_message_parts.append("\n" + "=" * 60)
    user_message_parts.append("【各专家分析意见】")

    for output in outputs:
        agent_name = agent_name_map.get(output.task_agent_id, f"Agent-{output.task_agent_id}")
        user_message_parts.append(f"\n--- {agent_name} ---")
        if output.output_text:
            # 限制每个 Agent 的输出长度，避免 Prompt 过长
            text = output.output_text
            if len(text) > 3000:
                text = text[:3000] + "\n...[内容过长，已截断]..."
            user_message_parts.append(text)
        else:
            user_message_parts.append("[该专家未生成有效分析]")

    # --- 汇总相似度检测结果 ---
    user_message_parts.append("\n" + "=" * 60)
    user_message_parts.append("【观点相似度分析】")
    if similarities:
        for s in similarities:
            user_message_parts.append(f"- {s.get('explanation', '')}")
    else:
        user_message_parts.append("未进行相似度分析或分析无结果。")

    # --- 汇总冲突检测结果 ---
    user_message_parts.append("\n" + "=" * 60)
    user_message_parts.append("【观点冲突检测】")
    high_conflicts = [c for c in conflicts if c.get("conflict_level") == "high"]
    if high_conflicts:
        user_message_parts.append(f"共发现 {len(high_conflicts)} 个高冲突维度：")
        for c in high_conflicts:
            user_message_parts.append(f"- {c.get('explanation', c.get('dimension', '?'))}")
    else:
        user_message_parts.append("各维度专家意见较为一致，未发现明显冲突。")

    if weighted_ranking:
        user_message_parts.append("\n" + "=" * 60)
        user_message_parts.append(format_ranking_for_summary(weighted_ranking))

    user_message_parts.append("\n请基于以上所有信息，生成你的综合建议报告。")

    user_message = "\n".join(user_message_parts)

    # =========================================================================
    # 第 2 步：调用大模型（本地 Qwen 或 API，由 LLM_BACKEND 决定）
    # =========================================================================
    logger.info("正在生成综合建议...")
    result = await llm_chat(
        SUMMARY_SYSTEM_PROMPT,
        user_message,
        temperature=0.5,
        max_new_tokens=2048,
        task_id=task_id,
        label="summary",
    )

    if result["success"] and result["text"]:
        logger.info("综合建议生成完成，长度: %d 字符", len(result["text"]))
        return {
            "success": True,
            "summary_text": result["text"],
            "error": None,
        }

    return {
        "success": False,
        "summary_text": None,
        "error": result.get("error") or "未知错误",
    }
