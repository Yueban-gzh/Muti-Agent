"""将请求体 Agent 配置（模板或自定义）解析为统一字段。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AgentTemplate
from schemas.task import AgentConfig
from services.exceptions import ServiceError


async def resolve_agent_config(
    db: AsyncSession,
    cfg: AgentConfig,
    decision_mode: str,
    index: int,
) -> dict:
    """
    返回 dict: agent_name, role_description, focus_area, tone,
    stance, template_id, extra_notes
    """
    template: AgentTemplate | None = None
    if cfg.template_id is not None:
        result = await db.execute(
            select(AgentTemplate).where(AgentTemplate.id == cfg.template_id)
        )
        template = result.scalar_one_or_none()
        if template is None:
            raise ServiceError(f"模板 ID {cfg.template_id} 不存在")
        if template.is_active != 1:
            raise ServiceError(f"模板「{template.name}」已禁用")

    agent_name = (cfg.agent_name or "").strip() or (template.name if template else "")
    if not agent_name:
        raise ServiceError(f"第 {index + 1} 个 Agent 缺少名称，请填写 agent_name 或 template_id")

    role_description = cfg.role_description or (template.role_description if template else None)
    focus_area = cfg.focus_area or (template.focus_area if template else None)
    tone = cfg.tone or (template.tone if template else None)

    stance = cfg.stance
    if decision_mode == "debate":
        if not stance or stance not in ("pro", "con", "judge", "neutral"):
            raise ServiceError(
                f"辩论模式下 Agent「{agent_name}」必须明确指定立场："
                "pro（支持方）、con（反对方）、judge（评审方）"
            )
    else:
        if not stance and template and template.default_stance:
            stance = template.default_stance
        stance = stance or "neutral"

    return {
        "agent_name": agent_name,
        "role_description": role_description,
        "focus_area": focus_area,
        "tone": tone,
        "stance": stance,
        "template_id": template.id if template else None,
        "extra_notes": (cfg.extra_notes or "").strip() or None,
    }


def validate_debate_stances(agents: list[dict]) -> None:
    stances = [a.get("stance") for a in agents]
    if "pro" not in stances or "con" not in stances:
        raise ServiceError("辩论模式至少需要一个支持方(pro)和一个反对方(con)")
    if stances.count("judge") > 1:
        raise ServiceError("辩论模式最多只能有一个评审方(judge)")
