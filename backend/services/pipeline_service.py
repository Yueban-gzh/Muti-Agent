"""后台 AI 分析流水线入口。"""

from ai.agent_core import process_task_background


async def run_task_pipeline(task_id: int) -> None:
    """触发多 Agent 分析流水线（异步后台任务）。"""
    await process_task_background(task_id)
