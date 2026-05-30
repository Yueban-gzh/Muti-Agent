"""
用户反馈相关 Pydantic Schema 定义
--------------------------------
定义用户提交决策反馈的请求和响应模型。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class FeedbackCreate(BaseModel):
    """
    用户提交反馈的请求体

    用户在查看分析结果后，选择采纳某个方案，
    系统保存此偏好数据供后续分析。
    """

    task_id: int = Field(
        ...,
        ge=1,
        description="关联的决策任务 ID",
    )
    chosen_type: str = Field(
        ...,
        pattern=r"^(agent|summary|none)$",
        description="采纳类型：agent（某个 Agent）/ summary（综合建议）/ none（暂不采纳）",
        examples=["agent"],
    )
    chosen_agent_id: Optional[int] = Field(
        default=None,
        description="采纳的 Agent ID（chosen_type=agent 时必填）",
        examples=[1],
    )
    comment: Optional[str] = Field(
        default=None,
        max_length=500,
        description="用户备注（最多 500 字）",
        examples=["创新增长派的观点更符合我们团队的方向"],
    )


class FeedbackResponse(BaseModel):
    """
    用户反馈的响应体
    """

    id: int = Field(..., description="反馈 ID")
    task_id: int = Field(..., description="关联任务 ID")
    user_id: int = Field(..., description="反馈用户 ID")
    chosen_type: str = Field(..., description="采纳类型")
    chosen_agent_id: Optional[int] = Field(default=None, description="采纳的 Agent ID")
    comment: Optional[str] = Field(default=None, description="用户备注")
    created_at: datetime = Field(..., description="反馈时间")

    model_config = ConfigDict(from_attributes=True)


class FeedbackStatistics(BaseModel):
    """
    反馈统计信息（管理员查看）
    """

    total_feedback_count: int = Field(default=0, description="总反馈数")
    agent_adoption_count: int = Field(default=0, description="采纳 Agent 的次数")
    summary_adoption_count: int = Field(default=0, description="采纳综合建议的次数")
    none_count: int = Field(default=0, description="暂不采纳的次数")
