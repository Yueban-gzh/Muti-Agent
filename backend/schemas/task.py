"""
任务相关 Pydantic Schema 定义
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AgentConfig(BaseModel):
    """单个 Agent 的配置：模板 ID 或自定义四字段（可并存）。"""
    agent_name: Optional[str] = Field(
        default=None, max_length=100, description="展示名称（无 template_id 时必填）"
    )
    role_description: Optional[str] = Field(default=None, description="角色/专业背景")
    focus_area: Optional[str] = Field(default=None, description="关注领域")
    tone: Optional[str] = Field(default=None, description="输出风格")
    stance: Optional[str] = Field(
        default=None,
        description="辩论立场 pro/con/neutral/judge",
    )
    template_id: Optional[int] = Field(default=None, ge=1, description="预设模板 ID")
    extra_notes: Optional[str] = Field(default=None, max_length=300, description="本案补充")

    @model_validator(mode="after")
    def require_name_or_template(self) -> "AgentConfig":
        if not self.template_id and not (self.agent_name and self.agent_name.strip()):
            raise ValueError("每个 Agent 需提供 template_id 或 agent_name")
        return self


class AgentConfigResponse(BaseModel):
    id: int
    task_id: int
    agent_name: str
    role_description: Optional[str] = None
    focus_area: Optional[str] = None
    tone: Optional[str] = None
    stance: Optional[str] = None
    template_id: Optional[int] = None
    extra_notes: Optional[str] = None
    sort_order: int = 0
    final_prompt: str
    stance_label: Optional[str] = None
    agent_display_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class TaskCreate(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    decision_mode: str = Field(..., examples=["multi_angle"])
    agent_count: int = Field(..., ge=2, le=5)
    agents: list[AgentConfig] = Field(..., min_length=2, max_length=5)
    weight_config: Optional[str] = None
    context_notes: Optional[str] = Field(default=None, max_length=1000)
    start_discussion: bool = Field(
        default=True,
        description="true=进入 discussing；false=仅创建",
    )
    legacy_auto_finalize: Optional[bool] = Field(
        default=None,
        description="true=跳过讨论直接跑旧版流水线（联调用）",
    )


class TaskResponse(BaseModel):
    task_id: int
    status: str
    message: str = "任务已创建"


class TaskStatusResponse(BaseModel):
    task_id: int
    status: str
    decision_mode: Optional[str] = None
    discussion_turns: int = 0
    max_discussion_turns: int = 30
    can_finalize: bool = False
    debate_exchange_rounds: int = 0
    error_message: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class AgentOutputResponse(BaseModel):
    id: int
    task_id: int
    task_agent_id: int
    agent_name: str = ""
    output_text: Optional[str] = None
    score_json: Optional[str] = None
    phase: str = "final"
    round: int = 1
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class SimilarityResultResponse(BaseModel):
    id: int
    task_id: int
    agent_id_1: int
    agent_id_2: int
    similarity: float
    explanation: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ConflictResultResponse(BaseModel):
    id: int
    task_id: int
    dimension: str
    max_score: float
    min_score: float
    conflict_level: str
    explanation: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class WeightedRankingItem(BaseModel):
    task_agent_id: int
    agent_name: str
    scores: Optional[dict[str, float]] = None
    total_score: Optional[float] = None
    rank: Optional[int] = None
    score_available: bool


class TaskResultResponse(BaseModel):
    task_id: int
    question: str
    decision_mode: str
    agent_count: int
    weight_config: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    final_summary: Optional[str] = None
    context_notes: Optional[str] = None
    discussion_summary: Optional[str] = None
    summary_method: Optional[str] = None
    created_at: datetime
    agents: list[AgentConfigResponse] = Field(default_factory=list)
    outputs: list[AgentOutputResponse] = Field(default_factory=list)
    messages: list[dict] = Field(default_factory=list)
    similarities: list[SimilarityResultResponse] = Field(default_factory=list)
    conflicts: list[ConflictResultResponse] = Field(default_factory=list)
    weighted_ranking: list[WeightedRankingItem] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)
