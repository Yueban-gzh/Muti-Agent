from typing import List, Dict, Any
from .auth import _mock_users_db
from .debate import _mock_tasks_db
from .feedback import _feedback_db
from datetime import datetime, timezone

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

def get_all_users() -> List[Dict[str, Any]]:
    return [
        {
            "id": u["id"],
            "username": u["username"],
            "role": u["role"],
            "created_at": u.get("created_at", _utcnow_iso())
        }
        for u in _mock_users_db.values()
    ]

def get_all_tasks(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    tasks = list(_mock_tasks_db.values())
    tasks.sort(key=lambda x: x["created_at"], reverse=True)
    result = []
    for t in tasks[offset:offset+limit]:
        result.append({
            "id": t["task_id"],
            "user_id": t["user_id"],
            "question": t["question"],
            "decision_mode": t["decision_mode"],
            "agent_count": t["agent_count"],
            "status": t["status"],
            "created_at": t["created_at"]
        })
    return result

def get_admin_stats() -> Dict[str, Any]:
    users = list(_mock_users_db.values())
    tasks = list(_mock_tasks_db.values())
    completed = sum(1 for t in tasks if t["status"] == "completed")
    failed = sum(1 for t in tasks if t["status"] == "failed")
    pending = len(tasks) - completed - failed
    return {
        "total_users": len(users),
        "total_admin_users": sum(1 for u in users if u["role"] == "admin"),
        "total_tasks": len(tasks),
        "completed_tasks": completed,
        "failed_tasks": failed,
        "pending_tasks": pending,
        "total_feedback": len(_feedback_db),
        "agent_adoption_count": sum(1 for f in _feedback_db if f["chosen_type"] == "agent"),
        "summary_adoption_count": sum(1 for f in _feedback_db if f["chosen_type"] == "summary"),
        "none_adoption_count": sum(1 for f in _feedback_db if f["chosen_type"] == "none"),
        "total_templates": 5,
        "active_templates": 5
    }

# 模板管理（简化，仅用于演示）
_templates = [
    {"id": 1, "name": "金·决断型", "role_description": "法务风控专家", "focus_area": "法律合规、失败风险", "tone": "严谨型", "is_active": 1, "created_at": _utcnow_iso()},
    {"id": 2, "name": "木·生长型", "role_description": "产品创新专家", "focus_area": "增长机会、长期价值", "tone": "鼓励型", "is_active": 1, "created_at": _utcnow_iso()},
]

def get_templates(include_inactive: bool = False) -> List[Dict]:
    if include_inactive:
        return _templates
    return [t for t in _templates if t["is_active"] == 1]

def create_template(data: Dict) -> Dict:
    new_id = max((t["id"] for t in _templates), default=0) + 1
    new = {
        "id": new_id,
        "name": data["name"],
        "role_description": data.get("role_description", ""),
        "focus_area": data.get("focus_area", ""),
        "tone": data.get("tone", ""),
        "is_active": data.get("is_active", 1),
        "created_at": _utcnow_iso()
    }
    _templates.append(new)
    return new

def update_template(template_id: int, data: Dict) -> Dict:
    for t in _templates:
        if t["id"] == template_id:
            t.update(data)
            return t
    return None

def delete_template(template_id: int) -> bool:
    for i, t in enumerate(_templates):
        if t["id"] == template_id:
            _templates.pop(i)
            return True
    return False

def get_logs(event_type: str = None, limit: int = 100) -> List[Dict]:
    # 模拟日志
    logs = [
        {"id": 1, "user_id": 1, "event_type": "login", "description": "用户登录", "created_at": _utcnow_iso()}
    ]
    if event_type:
        logs = [l for l in logs if l["event_type"] == event_type]
    return logs[-limit:]