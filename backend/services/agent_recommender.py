"""按问题关键词与决策模式推荐 Agent 模板组合。"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AgentTemplate

MODE_DEFAULT_NAMES: dict[str, list[str]] = {
    "multi_angle": ["木·生长型", "金·决断型", "土·稳健型"],
    "expert_consult": ["木·生长型", "火·行动型", "水·智慧型"],
    "risk_review": ["金·决断型", "土·稳健型", "火·行动型"],
    "debate": ["木·生长型", "金·决断型", "水·智慧型"],
}

RULES: list[dict] = [
    {
        "id": "tech_dev",
        "keywords": ["技术", "开发", "系统", "架构", "代码", "小程序", "app", "软件"],
        "modes": ["multi_angle", "expert_consult"],
        "names": ["火·行动型", "木·生长型", "土·稳健型"],
    },
    {
        "id": "startup",
        "keywords": ["创业", "市场", "推广", "融资", "商业"],
        "modes": ["expert_consult", "multi_angle"],
        "names": ["木·生长型", "水·智慧型", "土·稳健型"],
    },
    {
        "id": "risk",
        "keywords": ["风险", "上线", "投入", "合规", "安全"],
        "modes": ["risk_review", "debate", "multi_angle"],
        "names": ["金·决断型", "土·稳健型", "火·行动型"],
    },
    {
        "id": "debate_go",
        "keywords": ["是否", "要不要", "该不该", "值得", "应该"],
        "modes": ["debate"],
        "names": ["木·生长型", "金·决断型", "水·智慧型"],
    },
]


@dataclass
class RecommendResult:
    matched_rule_id: str | None
    hint: str
    agents: list[dict]


async def recommend_agents(
    db: AsyncSession,
    question: str,
    decision_mode: str,
    agent_count: int = 3,
) -> RecommendResult:
    q = question.lower()
    best_score = 0
    best_rule: dict | None = None
    for rule in RULES:
        score = sum(1 for kw in rule["keywords"] if kw in q)
        if decision_mode in rule["modes"]:
            score += 1
        if score > best_score:
            best_score = score
            best_rule = rule

    if best_rule and best_score > 0:
        names = best_rule["names"]
        rule_id = best_rule["id"]
        hint = f"根据问题关键词匹配规则「{rule_id}」，已推荐相应专家组合。"
    else:
        names = MODE_DEFAULT_NAMES.get(decision_mode, MODE_DEFAULT_NAMES["multi_angle"])
        rule_id = "default"
        hint = f"未命中特定关键词，使用「{decision_mode}」模式默认专家组合。"
    if decision_mode == "debate":
        hint += (
            " 辩论推荐 3 人（正+反+评审）；若选 2 人则无评审归纳。"
            " 采用后请确认每位辩手立场（支持方/反对方/评审方）。"
        )

    result = await db.execute(select(AgentTemplate).where(AgentTemplate.is_active == 1))
    templates = {t.name: t for t in result.scalars().all()}

    agents: list[dict] = []
    for i in range(min(agent_count, 5)):
        name = names[i % len(names)]
        tpl = templates.get(name)
        if not tpl:
            continue
        suggested = tpl.default_stance if decision_mode == "debate" else None
        entry = {
            "template_id": tpl.id,
            "agent_name": tpl.name,
            "role_description": tpl.role_description,
            "focus_area": tpl.focus_area,
            "tone": tpl.tone,
            "extra_notes": None,
        }
        if decision_mode == "debate":
            entry["suggested_stance"] = suggested
            entry["stance"] = None
        else:
            entry["stance"] = "neutral"
        agents.append(entry)

    while len(agents) < agent_count and len(agents) < 5:
        for name in names:
            if len(agents) >= agent_count:
                break
            tpl = templates.get(name)
            if tpl and not any(a["template_id"] == tpl.id for a in agents):
                entry = {
                    "template_id": tpl.id,
                    "agent_name": tpl.name,
                    "role_description": tpl.role_description,
                    "focus_area": tpl.focus_area,
                    "tone": tpl.tone,
                    "extra_notes": None,
                }
                if decision_mode == "debate":
                    entry["suggested_stance"] = tpl.default_stance
                else:
                    entry["stance"] = "neutral"
                agents.append(entry)

    return RecommendResult(matched_rule_id=rule_id, hint=hint, agents=agents)
