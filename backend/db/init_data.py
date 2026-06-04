"""
数据库初始化数据脚本
-------------------
在应用首次启动时插入默认数据（管理员账号、预设 Agent 模板）。
"""

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.security import get_password_hash
from db.models import User, AgentTemplate

logger = logging.getLogger("init_data")


DEFAULT_TEMPLATES = [
    {
        "name": "金·决断型",
        "display_alias": "风险审慎派",
        "role_description": "法务风控专家",
        "focus_area": "原则与规则、法律合规红线、失败风险与兜底方案",
        "tone": "严谨型",
        "default_stance": "con",
        "recommended_modes": ["multi_angle", "risk_review", "debate"],
        "sort_order": 1,
    },
    {
        "name": "木·生长型",
        "display_alias": "创新增长派",
        "role_description": "产品创新专家",
        "focus_area": "增长机会、长期价值、用户需求与市场趋势",
        "tone": "鼓励型",
        "default_stance": "pro",
        "recommended_modes": ["multi_angle", "expert_consult", "debate"],
        "sort_order": 2,
    },
    {
        "name": "水·智慧型",
        "display_alias": "战略协调派",
        "role_description": "战略分析专家",
        "focus_area": "全局视野、多维度权衡、灵活应变与备选方案",
        "tone": "中立型",
        "default_stance": "judge",
        "recommended_modes": ["multi_angle", "expert_consult", "debate"],
        "sort_order": 3,
    },
    {
        "name": "火·行动型",
        "display_alias": "技术执行派",
        "role_description": "项目执行专家",
        "focus_area": "执行可行性、落地速度、资源协调与团队动员",
        "tone": "激进型",
        "default_stance": "neutral",
        "recommended_modes": ["multi_angle", "expert_consult", "risk_review"],
        "sort_order": 4,
    },
    {
        "name": "土·稳健型",
        "display_alias": "成本控制派",
        "role_description": "财务成本专家",
        "focus_area": "成本投入与回报、预算控制、稳健经营与可持续性",
        "tone": "保守型",
        "default_stance": "neutral",
        "recommended_modes": ["multi_angle", "risk_review", "expert_consult"],
        "sort_order": 5,
    },
]


async def seed_default_data(db: AsyncSession) -> None:
    """插入默认管理员与 Agent 模板（幂等）。"""
    result = await db.execute(select(User).where(User.username == "admin"))
    if result.scalar_one_or_none() is None:
        db.add(
            User(
                username="admin",
                password_hash=get_password_hash("admin123456"),
                role="admin",
            )
        )
        await db.commit()
        logger.info("默认管理员账号已创建 (admin / admin123456)")

    for tpl in DEFAULT_TEMPLATES:
        modes_json = json.dumps(tpl["recommended_modes"], ensure_ascii=False)
        result = await db.execute(
            select(AgentTemplate).where(AgentTemplate.name == tpl["name"])
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            db.add(
                AgentTemplate(
                    name=tpl["name"],
                    role_description=tpl["role_description"],
                    focus_area=tpl["focus_area"],
                    tone=tpl["tone"],
                    default_stance=tpl.get("default_stance"),
                    recommended_modes=modes_json,
                    sort_order=tpl.get("sort_order", 0),
                    display_alias=tpl.get("display_alias"),
                    is_active=1,
                )
            )
        else:
            existing.default_stance = tpl.get("default_stance")
            existing.recommended_modes = modes_json
            existing.sort_order = tpl.get("sort_order", 0)
            existing.display_alias = tpl.get("display_alias")

    await db.commit()
    logger.info("预设 Agent 模板已就绪（%d 个）", len(DEFAULT_TEMPLATES))
