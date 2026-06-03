"""
Agent 模板相关 Pydantic Schema
-----------------------------
定义 Agent 预设模板的请求与响应模型。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# 请求模型
# ============================================================================


class TemplateCreate(BaseModel):
    """创建 Agent 模板的请求体"""
    name: str = Field(..., min_length=1, max_length=100, description="模板名称", examples=["创新增长派"])
    role_description: Optional[str] = Field(default=None, description="角色/专业背景", examples=["产品经理"])
    focus_area: Optional[str] = Field(default=None, description="关注领域", examples=["增长机会、长期价值"])
    tone: Optional[str] = Field(default=None, description="输出风格", examples=["鼓励型"])
    is_active: int = Field(default=1, ge=0, le=1, description="是否启用（1=启用，0=禁用）")


class TemplateUpdate(BaseModel):
    """更新 Agent 模板的请求体（所有字段可选）"""
    name: Optional[str] = Field(default=None, min_length=1, max_length=100, description="模板名称")
    role_description: Optional[str] = Field(default=None, description="角色/专业背景")
    focus_area: Optional[str] = Field(default=None, description="关注领域")
    tone: Optional[str] = Field(default=None, description="输出风格")
    is_active: Optional[int] = Field(default=None, ge=0, le=1, description="是否启用")


# ============================================================================
# 响应模型
# ============================================================================


class TemplateResponse(BaseModel):
    """Agent 模板的响应体"""
    id: int = Field(..., description="模板 ID")
    name: str = Field(..., description="模板名称")
    role_description: Optional[str] = Field(default=None, description="角色/专业背景")
    focus_area: Optional[str] = Field(default=None, description="关注领域")
    tone: Optional[str] = Field(default=None, description="输出风格")
    default_stance: Optional[str] = Field(default=None, description="辩论默认立场")
    recommended_modes: Optional[str] = Field(default=None, description="适用模式 JSON")
    sort_order: int = Field(default=0, description="排序")
    display_alias: Optional[str] = Field(default=None, description="展示别名")
    is_active: int = Field(..., description="是否启用")
    created_at: datetime = Field(..., description="创建时间")

    model_config = ConfigDict(from_attributes=True)


class TemplateListResponse(BaseModel):
    """模板列表响应（前端一键应用用）"""
    templates: list[TemplateResponse] = Field(default_factory=list, description="模板列表")
    total: int = Field(default=0, description="模板总数")
