"""
任务相关 Pydantic Schema 定义
-----------------------------
使用 Pydantic V2 定义决策任务创建、Agent 配置、任务状态查询
和结果获取的请求/响应模型。
第三阶段新增：相似度、冲突、综合建议相关模型。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# Agent 配置相关
# ============================================================================


class AgentConfig(BaseModel):
    """单个 Agent 的配置信息（请求体）"""
    agent_name: str = Field(..., min_length=1, max_length=100, description="Agent 展示名称", examples=["创新增长派"])
    role_description: Optional[str] = Field(default=None, description="角色/专业背景", examples=["产品经理"])
    focus_area: Optional[str] = Field(default=None, description="关注领域", examples=["增长机会、长期价值"])
    tone: Optional[str] = Field(default=None, description="输出风格", examples=["鼓励型"])


class AgentConfigResponse(BaseModel):
    """Agent 配置的完整响应（含数据库生成字段）"""
    id: int = Field(..., description="Agent 配置 ID")
    task_id: int = Field(..., description="所属任务 ID")
    agent_name: str = Field(..., description="Agent 名称")
    role_description: Optional[str] = Field(default=None, description="角色/背景描述")
    focus_area: Optional[str] = Field(default=None, description="关注领域")
    tone: Optional[str] = Field(default=None, description="输出风格")
    final_prompt: str = Field(..., description="最终 System Prompt")
    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# 决策任务创建
# ============================================================================


class TaskCreate(BaseModel):
    """创建决策任务的请求体"""
    question: str = Field(..., min_length=1, max_length=2000, description="决策问题原文",
                          examples=["我们团队是否应该开发一款校园二手交易小程序？"])
    decision_mode: str = Field(..., description="决策模式", examples=["multi_angle"])
    agent_count: int = Field(..., ge=2, le=5, description="Agent 数量（2~5）", examples=[3])
    agents: list[AgentConfig] = Field(..., min_length=2, max_length=5, description="Agent 配置列表")
    weight_config: Optional[str] = Field(default=None, description="用户自定义权重配置 JSON")


# ============================================================================
# 任务创建响应 & 状态查询
# ============================================================================


class TaskResponse(BaseModel):
    """创建任务后的即时响应"""
    task_id: int = Field(..., description="任务 ID")
    status: str = Field(default="pending", description="任务状态")
    message: str = Field(default="任务已提交，正在后台处理", description="操作提示")


class TaskStatusResponse(BaseModel):
    """任务状态轮询响应"""
    task_id: int = Field(..., description="任务 ID")
    status: str = Field(..., description="任务状态")
    error_message: Optional[str] = Field(default=None, description="错误信息")
    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Agent 输出
# ============================================================================


class AgentOutputResponse(BaseModel):
    """单个 Agent 输出的响应体"""
    id: int = Field(..., description="输出 ID")
    task_id: int = Field(..., description="所属任务 ID")
    task_agent_id: int = Field(..., description="所属 Agent 配置 ID")
    agent_name: str = Field(default="", description="Agent 名称")
    output_text: Optional[str] = Field(default=None, description="Agent 分析文本")
    score_json: Optional[str] = Field(default=None, description="六维评分 JSON")
    created_at: datetime = Field(..., description="输出生成时间")
    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# 第三阶段新增：相似度 & 冲突 & 综合建议
# ============================================================================


class SimilarityResultResponse(BaseModel):
    """语义相似度结果响应"""
    id: int = Field(..., description="相似度结果 ID")
    task_id: int = Field(..., description="所属任务 ID")
    agent_id_1: int = Field(..., description="Agent 1 ID")
    agent_id_2: int = Field(..., description="Agent 2 ID")
    similarity: float = Field(..., description="余弦相似度（0~1）")
    explanation: Optional[str] = Field(default=None, description="相似度分析说明")
    created_at: datetime = Field(..., description="计算时间")
    model_config = ConfigDict(from_attributes=True)


class ConflictResultResponse(BaseModel):
    """观点冲突检测结果响应"""
    id: int = Field(..., description="冲突结果 ID")
    task_id: int = Field(..., description="所属任务 ID")
    dimension: str = Field(..., description="冲突维度")
    max_score: float = Field(..., description="最高分")
    min_score: float = Field(..., description="最低分")
    conflict_level: str = Field(..., description="冲突等级（high / low）")
    explanation: Optional[str] = Field(default=None, description="冲突分析说明")
    created_at: datetime = Field(..., description="检测时间")
    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# 任务完整结果（第三阶段：包含相似度、冲突、综合建议）
# ============================================================================


class TaskResultResponse(BaseModel):
    """
    任务完整结果的响应体

    包含任务基本信息、所有 Agent 配置和输出、
    相似度检测结果、冲突检测结果和综合建议。
    """

    task_id: int = Field(..., description="任务 ID")
    question: str = Field(..., description="决策问题")
    decision_mode: str = Field(..., description="决策模式")
    agent_count: int = Field(..., description="Agent 数量")
    weight_config: Optional[str] = Field(default=None, description="权重配置 JSON")
    status: str = Field(..., description="任务状态")
    error_message: Optional[str] = Field(default=None, description="错误信息")
    final_summary: Optional[str] = Field(default=None, description="综合建议")
    created_at: datetime = Field(..., description="任务创建时间")

    # 关联数据
    agents: list[AgentConfigResponse] = Field(default_factory=list, description="Agent 配置列表")
    outputs: list[AgentOutputResponse] = Field(default_factory=list, description="Agent 输出结果列表")
    similarities: list[SimilarityResultResponse] = Field(default_factory=list, description="相似度检测结果")
    conflicts: list[ConflictResultResponse] = Field(default_factory=list, description="冲突检测结果")

    model_config = ConfigDict(from_attributes=True)
