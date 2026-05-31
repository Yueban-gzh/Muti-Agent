"""
数据库初始化数据脚本
-------------------
在应用首次启动时插入默认数据（管理员账号、预设 Agent 模板）。
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.security import get_password_hash
from db.models import User, AgentTemplate

logger = logging.getLogger("init_data")


# ============================================================================
# 预设 Agent 模板数据
# ============================================================================

DEFAULT_TEMPLATES = [
    {
        "name": "金·决断型",
        "role_description": "法务风控专家",
        "focus_area": "原则与规则、法律合规红线、失败风险与兜底方案",
        "tone": "严谨型",
    },
    {
        "name": "木·生长型",
        "role_description": "产品创新专家",
        "focus_area": "增长机会、长期价值、用户需求与市场趋势",
        "tone": "鼓励型",
    },
    {
        "name": "水·智慧型",
        "role_description": "战略分析专家",
        "focus_area": "全局视野、多维度权衡、灵活应变与备选方案",
        "tone": "中立型",
    },
    {
        "name": "火·行动型",
        "role_description": "项目执行专家",
        "focus_area": "执行可行性、落地速度、资源协调与团队动员",
        "tone": "激进型",
    },
    {
        "name": "土·稳健型",
        "role_description": "财务成本专家",
        "focus_area": "成本投入与回报、预算控制、稳健经营与可持续性",
        "tone": "保守型",
    },
]


async def seed_default_data(db: AsyncSession) -> None:
    """
    在数据库中插入默认的管理员账号和预设 Agent 模板。

    如果数据已存在则跳过，保证幂等性。
    """
    # --- 创建默认管理员 ---
    result = await db.execute(select(User).where(User.username == "admin"))
    if result.scalar_one_or_none() is None:
        admin_user = User(
            username="admin",
            password_hash=get_password_hash("admin123456"),
            role="admin",
        )
        db.add(admin_user)
        await db.commit()
        logger.info("默认管理员账号已创建 (admin / admin123456)")

    # --- 创建预设 Agent 模板 ---
    for tpl in DEFAULT_TEMPLATES:
        result = await db.execute(
            select(AgentTemplate).where(AgentTemplate.name == tpl["name"])
        )
        if result.scalar_one_or_none() is None:
            db.add(AgentTemplate(**tpl, is_active=1))

    await db.commit()
    logger.info(f"预设 Agent 模板已就绪（{len(DEFAULT_TEMPLATES)} 个）")
