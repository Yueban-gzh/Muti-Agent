"""
Agent 模板管理接口
-----------------
提供系统预设 Agent 模板的查询接口（前端一键应用）。
管理员可通过 /api/admin 下的接口进行模板的增删改。

所有接口挂载在 /api/templates 路由前缀下。
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user
from db.database import get_db
from db.models import User, AgentTemplate
from schemas.discussion import TemplateRecommendRequest, TemplateRecommendResponse
from schemas.template import TemplateResponse, TemplateListResponse
from services.agent_recommender import recommend_agents
from services.exceptions import ServiceError
from api.http_utils import service_error_to_http

# ============================================================================
# 路由初始化
# ============================================================================

router = APIRouter(prefix="/api/templates", tags=["Agent 模板"])


@router.post(
    "/recommend",
    response_model=TemplateRecommendResponse,
    summary="根据问题推荐 Agent 组合",
)
async def recommend_template_agents(
    body: TemplateRecommendRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await recommend_agents(
        db, body.question, body.decision_mode, body.agent_count
    )
    return {
        "matched_rule_id": result.matched_rule_id,
        "hint": result.hint,
        "agents": result.agents,
    }


# ============================================================================
# GET /api/templates/ — 获取所有启用的模板
# ============================================================================


@router.get(
    "/",
    response_model=TemplateListResponse,
    summary="获取 Agent 模板列表",
    description="返回所有启用的 Agent 预设模板，供前端一键应用。无需管理员权限。",
)
async def get_templates(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    查询所有启用的 Agent 模板。

    返回:
        TemplateListResponse: 包含模板列表和总数
    """
    # 仅返回启用的模板
    result = await db.execute(
        select(AgentTemplate)
        .where(AgentTemplate.is_active == 1)
        .order_by(AgentTemplate.sort_order, AgentTemplate.id)
    )
    templates = result.scalars().all()

    return {
        "templates": [TemplateResponse.model_validate(t) for t in templates],
        "total": len(templates),
    }


# ============================================================================
# GET /api/templates/all — 获取全部模板（含未启用，管理员用）
# ============================================================================


@router.get(
    "/all",
    response_model=TemplateListResponse,
    summary="获取全部模板（含未启用）",
    description="返回所有 Agent 模板（包括已禁用的），供管理员管理使用。",
)
async def get_all_templates(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    查询全部 Agent 模板（含未启用）。

    普通用户调用此接口会视为查询启用模板。
    管理员调用返回全部。
    """
    if current_user.role == "admin":
        result = await db.execute(
            select(AgentTemplate).order_by(AgentTemplate.id)
        )
    else:
        result = await db.execute(
            select(AgentTemplate)
            .where(AgentTemplate.is_active == 1)
            .order_by(AgentTemplate.sort_order, AgentTemplate.id)
        )

    templates = result.scalars().all()

    return {
        "templates": [TemplateResponse.model_validate(t) for t in templates],
        "total": len(templates),
    }
