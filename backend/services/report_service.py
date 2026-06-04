"""Markdown 决策报告生成（与 HTTP 层解耦）。"""

from __future__ import annotations

from datetime import datetime, timezone

from ai.constants import ALL_DIMENSIONS, DECISION_MODE_LABELS, DIMENSION_NAME_MAP
from ai.scoring_core import calculate_weighted_ranking
from db.models import DecisionTask


def build_decision_report_markdown(task: DecisionTask) -> str:
    """将已完成任务的分析结果排版为 Markdown 文本。"""
    agent_name_map = {a.id: a.agent_name for a in task.task_agents}
    agent_output_map = {o.task_agent_id: o for o in task.agent_outputs}
    mode_map = DECISION_MODE_LABELS

    lines: list[str] = [
        "# 多智能体决策分析报告",
        "",
        f"**生成时间**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## 一、决策问题",
        "",
        f"> {task.question}",
        "",
        "---",
        "",
        "## 二、分析配置",
        "",
        f"- **决策模式**: {mode_map.get(task.decision_mode, task.decision_mode)}",
        f"- **参与 Agent 数量**: {task.agent_count} 个",
    ]
    if task.weight_config:
        lines.append(f"- **用户权重**: `{task.weight_config}`")
    lines.extend(["", "### 参与分析的 Agent", ""])
    lines.append("| # | Agent 名称 | 专业背景 | 关注领域 | 输出风格 |")
    lines.append("|---|-----------|---------|---------|---------|")
    for i, agent in enumerate(task.task_agents, 1):
        lines.append(
            f"| {i} | {agent.agent_name} | {agent.role_description or '-'} | "
            f"{agent.focus_area or '-'} | {agent.tone or '-'} |"
        )

    lines.extend(["", "---", "", "## 三、各专家分析意见", ""])
    for agent in task.task_agents:
        lines.append(f"### {agent.agent_name}")
        lines.append("")
        output = agent_output_map.get(agent.id)
        if output and output.output_text:
            text = output.output_text.replace("\n## ", "\n#### ").replace("\n# ", "\n### ")
            lines.append(text)
        else:
            lines.append("> 该 Agent 未生成有效分析。")
        lines.append("")

    lines.extend(["---", "", "## 四、语义相似度分析", ""])
    if task.similarity_results:
        lines.append("| Agent 1 | Agent 2 | 余弦相似度 | 说明 |")
        lines.append("|---------|---------|-----------|------|")
        for sr in task.similarity_results:
            name1 = agent_name_map.get(sr.agent_id_1, f"ID:{sr.agent_id_1}")
            name2 = agent_name_map.get(sr.agent_id_2, f"ID:{sr.agent_id_2}")
            level = "⚠️ 高度相似" if sr.similarity >= 0.7 else "✓ 差异明显"
            lines.append(f"| {name1} | {name2} | {sr.similarity:.2%} | {level} |")
        lines.append("")
        for sr in task.similarity_results:
            if sr.explanation:
                lines.append(f"- {sr.explanation}")
        lines.append("")
    else:
        lines.extend(["> 未进行相似度分析或无有效数据。", ""])

    lines.extend(["---", "", "## 五、加权综合得分排名", ""])
    ranking = calculate_weighted_ranking(
        task.agent_outputs,
        agent_name_map,
        task.weight_config,
    )
    scored = [r for r in ranking if r.get("score_available")]
    if scored:
        lines.append("| 排名 | Agent | 综合得分 |")
        lines.append("|------|-------|---------|")
        for item in scored:
            lines.append(
                f"| {item['rank']} | {item['agent_name']} | {item['total_score']:.2f}/10 |"
            )
        lines.extend(["", "### 六维评分明细", ""])
        dim_headers = " | ".join(DIMENSION_NAME_MAP[dim] for dim in ALL_DIMENSIONS)
        lines.append(f"| Agent | {dim_headers} |")
        lines.append("|-------|" + "|".join(["------"] * len(ALL_DIMENSIONS)) + "|")
        for item in scored:
            if item.get("scores"):
                cells = " | ".join(
                    f"{item['scores'][dim]:.0f}" for dim in ALL_DIMENSIONS
                )
                lines.append(f"| {item['agent_name']} | {cells} |")
        lines.append("")
    else:
        lines.extend(["> 暂无有效评分数据。", ""])

    lines.extend(["---", "", "## 六、观点冲突检测", ""])
    high_conflicts = [c for c in task.conflict_results if c.conflict_level == "high"]
    if task.conflict_results:
        lines.extend(["### 冲突维度总览", ""])
        lines.append("| 维度 | 最高分 | 最低分 | 分差 | 冲突等级 |")
        lines.append("|------|-------|-------|-----|---------|")
        for cr in task.conflict_results:
            dim_cn = DIMENSION_NAME_MAP.get(cr.dimension, cr.dimension)
            diff = cr.max_score - cr.min_score
            level_emoji = "⚠️ 高冲突" if cr.conflict_level == "high" else "✓ 一致"
            lines.append(
                f"| {dim_cn} | {cr.max_score:.0f} | {cr.min_score:.0f} | "
                f"{diff:.0f} | {level_emoji} |"
            )
        lines.append("")
        if high_conflicts:
            lines.append(f"### ⚠️ 高冲突维度（{len(high_conflicts)} 个）")
            lines.append("")
            for cr in high_conflicts:
                if cr.explanation:
                    lines.append(f"- {cr.explanation}")
            lines.append("")
    else:
        lines.extend(["> 未进行冲突检测或无有效数据。", ""])

    lines.extend(["---", "", "## 七、综合建议", ""])
    if task.final_summary:
        lines.append(task.final_summary)
    else:
        lines.append("> 未生成综合建议。")
    lines.extend([
        "",
        "---",
        "",
        f"*本报告由「可配置多智能体决策辅助系统」自动生成 "
        f"（任务 ID: {task.id}）*",
    ])
    return "\n".join(lines)
