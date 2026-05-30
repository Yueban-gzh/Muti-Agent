"""
管理员后台相关 Pydantic Schema
-----------------------------
定义管理员查看系统统计、用户列表、全站任务等响应模型。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# 用户管理
# ============================================================================


class AdminUserResponse(BaseModel):
    """管理员视角下的用户信息（含 role 字段）"""
    id: int = Field(..., description="用户 ID")
    username: str = Field(..., description="用户名")
    role: str = Field(..., description="角色")
    created_at: datetime = Field(..., description="注册时间")

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# 任务管理
# ============================================================================


class AdminTaskResponse(BaseModel):
    """管理员视角下的任务摘要"""
    id: int = Field(..., description="任务 ID")
    user_id: int = Field(..., description="所属用户 ID")
    username: str = Field(default="", description="用户名")
    question: str = Field(..., description="决策问题")
    decision_mode: str = Field(..., description="决策模式")
    agent_count: int = Field(..., description="Agent 数量")
    status: str = Field(..., description="任务状态")
    created_at: datetime = Field(..., description="创建时间")

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# 日志管理
# ============================================================================


class LogResponse(BaseModel):
    """操作日志响应体"""
    id: int = Field(..., description="日志 ID")
    user_id: Optional[int] = Field(default=None, description="操作用户 ID")
    event_type: str = Field(..., description="事件类型")
    description: Optional[str] = Field(default=None, description="事件描述")
    created_at: datetime = Field(..., description="事件时间")

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# 全局统计数据
# ============================================================================


class AdminStatsResponse(BaseModel):
    """管理员全局数据看板响应体"""
    # 用户统计
    total_users: int = Field(default=0, description="总用户数")
    total_admin_users: int = Field(default=0, description="管理员数量")

    # 任务统计
    total_tasks: int = Field(default=0, description="总任务数")
    completed_tasks: int = Field(default=0, description="已完成任务数")
    failed_tasks: int = Field(default=0, description="失败任务数")
    pending_tasks: int = Field(default=0, description="处理中任务数")

    # 反馈统计
    total_feedback: int = Field(default=0, description="总反馈数")
    agent_adoption_count: int = Field(default=0, description="采纳 Agent 次数")
    summary_adoption_count: int = Field(default=0, description="采纳综合建议次数")
    none_adoption_count: int = Field(default=0, description="暂不采纳次数")

    # 模板统计
    total_templates: int = Field(default=0, description="Agent 模板总数")
    active_templates: int = Field(default=0, description="启用的模板数")
