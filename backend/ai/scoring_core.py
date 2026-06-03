"""
加权评分与排名模块
-----------------
根据 Agent 输出的六维 score_json 和用户 weight_config，
计算每个 Agent 的加权综合得分并排名。
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from ai.constants import ALL_DIMENSIONS
from ai.prompt_builder import build_default_weight_config

logger = logging.getLogger("scoring_core")


def parse_weight_config(weight_config: Optional[str]) -> dict[str, float]:
    """解析权重 JSON，缺失或非法时回退默认权重。"""
    raw = weight_config or build_default_weight_config()
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("weight_config 解析失败，使用默认权重")
        parsed = json.loads(build_default_weight_config())

    if not isinstance(parsed, dict):
        parsed = json.loads(build_default_weight_config())

    weights = {dim: float(parsed.get(dim, 0.0)) for dim in ALL_DIMENSIONS}
    total = sum(weights.values())
    if total <= 0:
        return {k: float(v) for k, v in json.loads(build_default_weight_config()).items()}
    if abs(total - 1.0) > 0.001:
        weights = {dim: val / total for dim, val in weights.items()}
    return weights


def parse_score_json(score_json: Optional[str]) -> Optional[dict[str, float]]:
    """解析 Agent 六维评分；缺维或非法时返回 None。"""
    if not score_json:
        return None
    try:
        raw = json.loads(score_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(raw, dict):
        return None

    scores: dict[str, float] = {}
    for dim in ALL_DIMENSIONS:
        val = raw.get(dim)
        if val is None:
            return None
        try:
            score = float(val)
        except (TypeError, ValueError):
            return None
        scores[dim] = max(1.0, min(10.0, score))
    return scores


def compute_weighted_total(
    scores: dict[str, float],
    weights: dict[str, float],
) -> float:
    """加权综合得分（1~10）。"""
    return sum(scores[dim] * weights[dim] for dim in ALL_DIMENSIONS)


def calculate_weighted_ranking(
    outputs: list,
    agent_name_map: Optional[dict[int, str]] = None,
    weight_config: Optional[str] = None,
) -> list[dict]:
    """
    计算各 Agent 加权得分并排名。

    返回列表按 rank 升序（未评分的排在末尾，rank 为 null）。
    每项字段:
        task_agent_id, agent_name, scores, total_score, rank, score_available
    """
    if agent_name_map is None:
        agent_name_map = {}

    weights = parse_weight_config(weight_config)
    entries: list[dict] = []

    for output in outputs:
        agent_id = output.task_agent_id
        agent_name = agent_name_map.get(agent_id, f"Agent-{agent_id}")
        scores = parse_score_json(output.score_json)

        if scores is None:
            entries.append({
                "task_agent_id": agent_id,
                "agent_name": agent_name,
                "scores": None,
                "total_score": None,
                "rank": None,
                "score_available": False,
            })
            continue

        total = compute_weighted_total(scores, weights)
        entries.append({
            "task_agent_id": agent_id,
            "agent_name": agent_name,
            "scores": {dim: round(scores[dim], 1) for dim in ALL_DIMENSIONS},
            "total_score": round(total, 2),
            "rank": None,
            "score_available": True,
        })

    scored = [e for e in entries if e["score_available"]]
    scored.sort(key=lambda x: (-x["total_score"], x["task_agent_id"]))

    for idx, entry in enumerate(scored, start=1):
        entry["rank"] = idx

    unscored = [e for e in entries if not e["score_available"]]
    result = scored + unscored

    if scored:
        top = scored[0]
        logger.info(
            "加权排名完成: %d 个有效评分，最高「%s」%.2f 分",
            len(scored),
            top["agent_name"],
            top["total_score"],
        )
    else:
        logger.warning("无有效 score_json，跳过加权排名")

    return result


def format_ranking_for_summary(ranking: list[dict]) -> str:
    """将排名格式化为综合建议 Prompt 的补充文本。"""
    lines = ["【加权综合得分排名】"]
    scored = [r for r in ranking if r.get("score_available")]
    if not scored:
        lines.append("暂无有效评分数据（部分 Agent 未输出六维 JSON）。")
        return "\n".join(lines)

    for item in scored:
        lines.append(
            f"- 第 {item['rank']} 名: 「{item['agent_name']}」"
            f" 综合得分 {item['total_score']:.2f}/10"
        )
    return "\n".join(lines)
