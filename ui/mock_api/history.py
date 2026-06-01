from typing import List, Dict, Any, Optional
from .debate import _mock_tasks_db

def get_history(user_id: int) -> List[Dict[str, Any]]:
    history = []
    for task in _mock_tasks_db.values():
        if task["user_id"] == user_id:
            history.append({
                "task_id": task["task_id"],
                "question": task["question"],
                "status": task["status"],
                "created_at": task["created_at"]
            })
    history.sort(key=lambda x: x["task_id"], reverse=True)
    return history

def export_report(task_id: int) -> str:
    # 简单返回 Markdown 内容
    return f"# 决策报告\n\n任务ID: {task_id}\n\n## 分析摘要\n模拟报告内容。"