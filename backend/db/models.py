"""
数据表模型定义
-------------
使用 SQLAlchemy ORM 定义数据库中的所有数据表模型。
包含用户、决策任务、Agent 配置、Agent 输出、相似度、冲突和反馈模型。
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, Float, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db.database import Base


class User(Base):
    """用户表模型"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="用户唯一标识")
    username = Column(String(50), unique=True, nullable=False, index=True, comment="用户名（唯一）")
    password_hash = Column(String(128), nullable=False, comment="bcrypt 哈希密码")
    role = Column(String(10), nullable=False, default="user", comment="用户角色（user / admin）")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="账号创建时间")

    decision_tasks = relationship("DecisionTask", back_populates="user", lazy="selectin")
    feedbacks = relationship("UserFeedback", back_populates="user", lazy="selectin")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"


class DecisionTask(Base):
    """决策任务表（第三阶段新增 final_summary 字段）"""
    __tablename__ = "decision_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="任务唯一标识")
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="所属用户 ID")
    question = Column(Text, nullable=False, comment="决策问题原文")
    decision_mode = Column(String(30), nullable=False, comment="决策模式")
    agent_count = Column(Integer, nullable=False, comment="Agent 数量")
    weight_config = Column(Text, nullable=True, comment="用户权重配置 JSON")
    status = Column(String(20), nullable=False, default="discussing", comment="任务状态")
    error_message = Column(Text, nullable=True, comment="错误信息")

    # 第三阶段新增：综合建议
    final_summary = Column(Text, nullable=True, comment="大模型生成的综合建议")

    # 交流期 → 收束期
    context_notes = Column(Text, nullable=True, comment="任务背景说明")
    discussion_turns = Column(Integer, nullable=False, default=0, comment="用户发言轮次")
    debate_exchange_rounds = Column(
        Integer, nullable=False, default=0, comment="辩手自主交锋轮次（用户未发言）"
    )
    discussion_summary = Column(Text, nullable=True, comment="讨论纪要")
    summary_method = Column(String(20), nullable=True, comment="纪要生成方式 llm/rule_fallback")
    finalized_at = Column(DateTime(timezone=True), nullable=True, comment="收束完成时间")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="任务创建时间")

    # 关联关系
    user = relationship("User", back_populates="decision_tasks")
    discussion_messages = relationship(
        "DiscussionMessage",
        back_populates="task",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="DiscussionMessage.seq",  # noqa: RUF100
    )
    task_agents = relationship("TaskAgent", back_populates="task", lazy="selectin", cascade="all, delete-orphan")
    agent_outputs = relationship("AgentOutput", back_populates="task", lazy="selectin", cascade="all, delete-orphan")
    similarity_results = relationship("SimilarityResult", back_populates="task", lazy="selectin", cascade="all, delete-orphan")
    conflict_results = relationship("ConflictResult", back_populates="task", lazy="selectin", cascade="all, delete-orphan")
    feedbacks = relationship("UserFeedback", back_populates="task", lazy="selectin", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<DecisionTask(id={self.id}, status='{self.status}', mode='{self.decision_mode}')>"


class TaskAgent(Base):
    """任务 Agent 配置表"""
    __tablename__ = "task_agents"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="Agent 配置唯一标识")
    task_id = Column(Integer, ForeignKey("decision_tasks.id", ondelete="CASCADE"), nullable=False, index=True, comment="所属任务 ID")
    agent_name = Column(String(100), nullable=False, comment="Agent 名称")
    role_description = Column(Text, nullable=True, comment="角色/专业背景描述")
    focus_area = Column(Text, nullable=True, comment="关注领域")
    tone = Column(String(50), nullable=True, comment="输出风格")
    final_prompt = Column(Text, nullable=False, comment="收束期 System Prompt")
    stance = Column(String(20), nullable=True, comment="辩论立场 pro/con/neutral/judge")
    template_id = Column(Integer, ForeignKey("agent_templates.id", ondelete="SET NULL"), nullable=True)
    extra_notes = Column(Text, nullable=True, comment="用户本案补充")
    sort_order = Column(Integer, nullable=False, default=0, comment="展示排序")

    task = relationship("DecisionTask", back_populates="task_agents")
    agent_outputs = relationship("AgentOutput", back_populates="task_agent", lazy="selectin", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<TaskAgent(id={self.id}, name='{self.agent_name}', task_id={self.task_id})>"


class AgentOutput(Base):
    """Agent 输出表"""
    __tablename__ = "agent_outputs"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="输出唯一标识")
    task_id = Column(Integer, ForeignKey("decision_tasks.id", ondelete="CASCADE"), nullable=False, index=True, comment="所属任务 ID")
    task_agent_id = Column(Integer, ForeignKey("task_agents.id", ondelete="CASCADE"), nullable=False, comment="所属 Agent 配置 ID")
    output_text = Column(Text, nullable=True, comment="Agent 分析文本")
    score_json = Column(Text, nullable=True, comment="六维评分 JSON")
    phase = Column(String(20), nullable=False, default="final", comment="输出阶段 final")
    round = Column(Integer, nullable=False, default=1, comment="轮次")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="输出生成时间")

    task = relationship("DecisionTask", back_populates="agent_outputs")
    task_agent = relationship("TaskAgent", back_populates="agent_outputs")

    def __repr__(self) -> str:
        agent_name = self.task_agent.agent_name if self.task_agent else "?"
        return f"<AgentOutput(id={self.id}, agent='{agent_name}', task_id={self.task_id})>"


# ============================================================================
# 第三阶段新增模型
# ============================================================================


class SimilarityResult(Base):
    """
    语义相似度检测结果表

    存储 Agent 输出两两之间的余弦相似度计算结果，
    用于判断不同 Agent 观点是否过于重复。
    """
    __tablename__ = "similarity_results"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="相似度结果唯一标识")
    task_id = Column(Integer, ForeignKey("decision_tasks.id", ondelete="CASCADE"), nullable=False, index=True, comment="所属任务 ID")

    # 参与比较的两个 Agent Output ID
    agent_id_1 = Column(Integer, ForeignKey("task_agents.id", ondelete="CASCADE"), nullable=False, comment="Agent 1 的 ID")
    agent_id_2 = Column(Integer, ForeignKey("task_agents.id", ondelete="CASCADE"), nullable=False, comment="Agent 2 的 ID")

    # 余弦相似度值（0~1，1 表示完全相同）
    similarity = Column(Float, nullable=False, comment="余弦相似度（0~1）")

    # 自然语言解释说明
    explanation = Column(Text, nullable=True, comment="相似度分析说明")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="计算时间")

    # 关联关系
    task = relationship("DecisionTask", back_populates="similarity_results")
    agent_1 = relationship("TaskAgent", foreign_keys=[agent_id_1])
    agent_2 = relationship("TaskAgent", foreign_keys=[agent_id_2])

    def __repr__(self) -> str:
        return f"<SimilarityResult(id={self.id}, sim={self.similarity:.3f}, task_id={self.task_id})>"


class ConflictResult(Base):
    """
    观点冲突检测结果表

    存储各维度评分的冲突检测结果，
    基于评分差异判断 Agent 之间在哪些维度存在分歧。
    """
    __tablename__ = "conflict_results"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="冲突结果唯一标识")
    task_id = Column(Integer, ForeignKey("decision_tasks.id", ondelete="CASCADE"), nullable=False, index=True, comment="所属任务 ID")

    # 冲突维度名称（如：benefit, cost, risk, tech, exec, long_term）
    dimension = Column(String(30), nullable=False, comment="冲突维度")

    # 该维度的最高分和最低分
    max_score = Column(Float, nullable=False, comment="最高分")
    min_score = Column(Float, nullable=False, comment="最低分")

    # 冲突等级：high（差值>=4）/ low（差值<4）
    conflict_level = Column(String(10), nullable=False, comment="冲突等级（high / low）")

    # 自然语言解释：说明哪两个 Agent 分歧最大
    explanation = Column(Text, nullable=True, comment="冲突分析说明")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="检测时间")

    # 关联关系
    task = relationship("DecisionTask", back_populates="conflict_results")

    def __repr__(self) -> str:
        return f"<ConflictResult(id={self.id}, dim='{self.dimension}', level='{self.conflict_level}', task_id={self.task_id})>"


class UserFeedback(Base):
    """
    用户反馈表

    存储用户对决策分析结果的采纳选择，
    用于收集偏好数据、辅助后续优化。
    """
    __tablename__ = "user_feedback"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="反馈唯一标识")
    task_id = Column(Integer, ForeignKey("decision_tasks.id", ondelete="CASCADE"), nullable=False, index=True, comment="所属任务 ID")
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="反馈用户 ID")

    # 采纳类型：agent（采纳某个 Agent）/ summary（采纳综合建议）/ none（暂不采纳）
    chosen_type = Column(String(20), nullable=False, comment="采纳类型（agent / summary / none）")

    # 若采纳某个 Agent，记录其 ID；否则为 NULL
    chosen_agent_id = Column(Integer, ForeignKey("task_agents.id", ondelete="SET NULL"), nullable=True, comment="采纳的 Agent ID（可空）")

    # 用户备注
    comment = Column(Text, nullable=True, comment="用户备注")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="反馈时间")

    # 关联关系
    task = relationship("DecisionTask", back_populates="feedbacks")
    user = relationship("User", back_populates="feedbacks")
    chosen_agent = relationship("TaskAgent", foreign_keys=[chosen_agent_id])

    def __repr__(self) -> str:
        return f"<UserFeedback(id={self.id}, type='{self.chosen_type}', task_id={self.task_id})>"


# ============================================================================
# 第四阶段新增模型：Agent 模板 + 操作日志
# ============================================================================


class AgentTemplate(Base):
    """
    Agent 模板表

    存储系统预设的 Agent 人设模板，供用户快速选择应用。
    管理员可通过后台接口对模板进行增删改查。
    """
    __tablename__ = "agent_templates"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="模板唯一标识")
    name = Column(String(100), nullable=False, unique=True, comment="模板名称（如：创新增长派）")
    role_description = Column(Text, nullable=True, comment="角色/专业背景描述")
    focus_area = Column(Text, nullable=True, comment="关注领域")
    tone = Column(String(50), nullable=True, comment="输出风格")
    is_active = Column(Integer, nullable=False, default=1, comment="是否启用（1=启用，0=禁用）")
    default_stance = Column(String(20), nullable=True, comment="辩论默认立场")
    recommended_modes = Column(Text, nullable=True, comment="推荐适用模式 JSON 数组")
    sort_order = Column(Integer, nullable=False, default=0, comment="排序")
    display_alias = Column(String(100), nullable=True, comment="展示别名")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="创建时间")

    def __repr__(self) -> str:
        return f"<AgentTemplate(id={self.id}, name='{self.name}', active={self.is_active})>"


class OperationLog(Base):
    """
    操作日志表

    记录系统中的关键操作事件，包括用户行为、AI 调用和系统异常，
    供管理员审计和排查问题使用。
    """
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="日志唯一标识")
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True, comment="操作用户 ID（系统事件可为空）")
    event_type = Column(String(50), nullable=False, index=True, comment="事件类型")
    description = Column(Text, nullable=True, comment="事件描述")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="事件时间")

    # 关联关系
    user = relationship("User", foreign_keys=[user_id])

    def __repr__(self) -> str:
        return f"<OperationLog(id={self.id}, type='{self.event_type}')>"


class DiscussionMessage(Base):
    """讨论交流消息表"""
    __tablename__ = "discussion_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(
        Integer, ForeignKey("decision_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seq = Column(Integer, nullable=False, comment="消息序号")
    role = Column(String(20), nullable=False, comment="user/agent/system")
    task_agent_id = Column(
        Integer, ForeignKey("task_agents.id", ondelete="SET NULL"), nullable=True
    )
    target_agent_id = Column(
        Integer, ForeignKey("task_agents.id", ondelete="SET NULL"), nullable=True
    )
    reply_scope = Column(String(30), nullable=True, comment="回复范围")
    content = Column(Text, nullable=False, comment="消息正文")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    task = relationship("DecisionTask", back_populates="discussion_messages")
    task_agent = relationship("TaskAgent", foreign_keys=[task_agent_id])

    def __repr__(self) -> str:
        return f"<DiscussionMessage(id={self.id}, task_id={self.task_id}, seq={self.seq}, role={self.role})>"
