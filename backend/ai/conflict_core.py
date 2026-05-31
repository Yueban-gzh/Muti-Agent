"""
观点冲突检测模块
---------------
基于 Agent 输出的六维评分 JSON，检测各维度上是否存在明显分歧。
使用规则引擎：某维度最高分与最低分差值 >= 4 则判定为高冲突。

相较于复杂 NLP 推理，评分差异检测更稳定、可解释且符合 PRD 要求。
"""

import json
import logging

logger = logging.getLogger("conflict_core")

# ============================================================================
# 配置常量
# ============================================================================

# 冲突阈值：维度最高分 - 最低分 >= 此值时判定为高冲突
HIGH_CONFLICT_THRESHOLD = 4

# 维度中文名映射（与 prompt_builder 保持一致）
DIMENSION_NAME_MAP = {
    "benefit": "收益潜力",
    "cost": "成本可控性",
    "risk": "风险可控性",
    "tech": "技术可行性",
    "exec": "执行可行性",
    "long_term": "长期价值",
}

# 所有需要检测的维度
ALL_DIMENSIONS = ["benefit", "cost", "risk", "tech", "exec", "long_term"]


# ============================================================================
# 冲突检测入口
# ============================================================================


def detect_conflicts(
    outputs: list,
    agent_name_map: dict[int, str] | None = None,
) -> list[dict]:
    """
    检测多个 Agent 在各维度上的评分冲突。

    处理流程:
        1. 解析每个 Agent 的 score_json
        2. 按维度汇总所有 Agent 的评分
        3. 对每个维度，计算 max - min 的差值
        4. 差值 >= 4 的维度标记为高冲突，找出分歧最大的两个 Agent

    参数:
        outputs: AgentOutput ORM 对象列表
        agent_name_map: {agent_id: agent_name} 映射

    返回:
        list[dict]: 冲突结果列表，每个元素包含:
            - task_id: int
            - dimension: str (维度 key)
            - max_score: float
            - min_score: float
            - conflict_level: str ("high" / "low")
            - explanation: str
    """
    if agent_name_map is None:
        agent_name_map = {}

    results: list[dict] = []

    # --- 第 1 步：解析每个 Agent 的评分 ---
    # agent_scores: [{"agent_id": 1, "agent_name": "X", "scores": {...}}, ...]
    agent_scores: list[dict] = []

    for output in outputs:
        if not output.score_json:
            logger.warning(
                f"AgentOutput id={output.id} 缺少 score_json，跳过冲突检测"
            )
            continue

        try:
            scores = json.loads(output.score_json)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"AgentOutput id={output.id} score_json 解析失败: {e}")
            continue

        # 验证评分格式
        if not isinstance(scores, dict):
            logger.warning(f"AgentOutput id={output.id} score_json 不是 dict 格式")
            continue

        agent_name = agent_name_map.get(output.task_agent_id, f"Agent-{output.task_agent_id}")
        agent_scores.append({
            "agent_id": output.task_agent_id,
            "agent_name": agent_name,
            "scores": scores,
        })

    if len(agent_scores) < 2:
        logger.info("有效评分数据少于 2 个，跳过冲突检测")
        return results

    logger.info(f"开始冲突检测: {len(agent_scores)} 个 Agent, {len(ALL_DIMENSIONS)} 个维度")

    # --- 第 2 步：按维度检测冲突 ---
    task_id = outputs[0].task_id if outputs else 0

    for dim in ALL_DIMENSIONS:
        # 收集该维度下所有 Agent 的评分
        dim_scores: list[tuple[int, str, float]] = []  # (agent_id, agent_name, score)

        for as_ in agent_scores:
            score = as_["scores"].get(dim)
            if score is not None and isinstance(score, (int, float)):
                dim_scores.append((as_["agent_id"], as_["agent_name"], float(score)))

        if len(dim_scores) < 2:
            continue

        # 找出最高分和最低分
        max_entry = max(dim_scores, key=lambda x: x[2])
        min_entry = min(dim_scores, key=lambda x: x[2])
        score_diff = max_entry[2] - min_entry[2]

        dim_cn = DIMENSION_NAME_MAP.get(dim, dim)

        # 判定冲突等级
        if score_diff >= HIGH_CONFLICT_THRESHOLD:
            conflict_level = "high"
            explanation = (
                f"在「{dim_cn}」维度上存在明显分歧："
                f"「{max_entry[1]}」评分最高（{max_entry[2]:.0f} 分），"
                f"「{min_entry[1]}」评分最低（{min_entry[2]:.0f} 分），"
                f"分差为 {score_diff:.0f} 分（阈值 ≥ {HIGH_CONFLICT_THRESHOLD}）。"
                f"建议关注双方在该维度的具体论述。"
            )
            logger.info(f"高冲突维度: {dim_cn}, 差值={score_diff:.0f}")
        else:
            conflict_level = "low"
            explanation = (
                f"在「{dim_cn}」维度上 Agent 意见较为一致，"
                f"最高分 {max_entry[2]:.0f}（{max_entry[1]}），"
                f"最低分 {min_entry[2]:.0f}（{min_entry[1]}），"
                f"分差 {score_diff:.0f} 在可接受范围内。"
            )

        results.append({
            "task_id": task_id,
            "dimension": dim,
            "max_score": round(max_entry[2], 1),
            "min_score": round(min_entry[2], 1),
            "conflict_level": conflict_level,
            "explanation": explanation,
        })

    high_count = sum(1 for r in results if r["conflict_level"] == "high")
    logger.info(f"冲突检测完成: {len(results)} 个维度, {high_count} 个高冲突")
    return results
