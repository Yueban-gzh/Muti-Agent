from typing import List, Dict, Any
from .debate import _mock_tasks_db

def get_user_history(user_id: int) -> List[Dict[str, Any]]:
    tasks = []
    for task in _mock_tasks_db.values():
        if task.get("user_id") == user_id:
            tasks.append({
                "id": task["task_id"],
                "question": task["question"],
                "decision_mode": task["decision_mode"],
                "agent_count": task["agent_count"],
                "status": task["status"],
                "created_at": task["created_at"]
            })
    tasks.sort(key=lambda x: x["created_at"], reverse=True)
    return tasks

def export_report(task_id: int) -> str:
    # 简单返回 Markdown 内容
    return f"# 决策报告\n\n任务ID: {task_id}\n\n模拟报告内容。"