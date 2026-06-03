"""操作日志 event_type 常量（与 GET /api/admin/logs?event_type= 筛选一致）。"""

# 用户行为
USER_REGISTER = "user.register"
USER_LOGIN = "user.login"

# 任务生命周期
TASK_CREATE = "task.create"
TASK_DISCUSS_MESSAGE = "task.discuss.message"
TASK_FINALIZE_START = "task.finalize.start"
TASK_PROCESSING = "task.processing"
TASK_COMPLETED = "task.completed"
TASK_FAILED = "task.failed"

# AI 异常
AGENT_ALL_FAILED = "agent.all_failed"

# 用户反馈
FEEDBACK_VOTE = "feedback.vote"

# 系统
LLM_LOAD_FAILED = "llm.load_failed"
