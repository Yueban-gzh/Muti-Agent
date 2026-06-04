"""讨论交流相关 Schema。"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class DiscussionMessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=500)
    reply_scope: str = Field(
        default="all_brief",
        description=(
            "非辩论模式请用 all_brief（全体专家各一条，其他 scope 会被忽略）；"
            "辩论模式请用 debate_round（支持→反对→评审，其他 scope 会被忽略）"
        ),
        pattern=r"^(single|pro_side|con_side|judge|all_brief|debate_round)$",
    )
    target_agent_id: Optional[int] = Field(
        default=None,
        ge=1,
        description="已废弃：交流期不再按 Agent 定向，该字段会被忽略",
    )


class DiscussionMessageResponse(BaseModel):
    id: int
    task_id: int
    seq: int
    role: str
    task_agent_id: Optional[int] = None
    target_agent_id: Optional[int] = None
    reply_scope: Optional[str] = None
    content: str
    agent_name: Optional[str] = None
    stance: Optional[str] = None
    stance_label: Optional[str] = None
    agent_display_name: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class DebateRosterItem(BaseModel):
    task_agent_id: int
    agent_name: str
    stance: Optional[str] = None
    stance_label: Optional[str] = None
    agent_display_name: Optional[str] = None
    role_description: Optional[str] = None


class DiscussionMessageBatchResponse(BaseModel):
    user_message: Optional[DiscussionMessageResponse] = None
    agent_messages: list[DiscussionMessageResponse] = Field(default_factory=list)
    debate_round: bool = Field(default=False, description="是否完成了一轮三方交锋")
    step_type: str = Field(
        default="user_debate_round",
        description="user_debate_round | agent_exchange | system",
    )
    system_message: Optional[DiscussionMessageResponse] = None


class DebateAgentExchangeResponse(BaseModel):
    """用户不发言，辩手继续交锋一轮。"""
    system_message: Optional[DiscussionMessageResponse] = None
    agent_messages: list[DiscussionMessageResponse] = Field(default_factory=list)
    debate_exchange_round: int = Field(..., description="当前辩手自主交锋轮次")
    step_type: str = "agent_exchange"


class TemplateRecommendRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    decision_mode: str = Field(default="multi_angle")
    agent_count: int = Field(default=3, ge=2, le=5)


class TemplateRecommendResponse(BaseModel):
    matched_rule_id: Optional[str] = None
    hint: str
    agents: list[dict]
