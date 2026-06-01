from typing import List, Dict, Any, Optional
from .auth import _mock_users_db
from .debate import _mock_tasks_db

# ---------- 模板数据 ----------
_templates: List[Dict] = [
    {
        "id": 1,
        "name": "金·决断型",
        "role_description": "法务风控专家",
        "focus_area": "法律合规、失败风险",
        "tone": "严谨型",
        "is_active": 1
    },
    {
        "id": 2,
        "name": "木·生长型",
        "role_description": "产品创新专家",
        "focus_area": "增长机会、长期价值",
        "tone": "鼓励型",
        "is_active": 1
    },
    {
        "id": 3,
        "name": "水·智慧型",
        "role_description": "战略分析专家",
        "focus_area": "全局视野、灵活应变",
        "tone": "中立型",
        "is_active": 1
    },
    {
        "id": 4,
        "name": "火·行动型",
        "role_description": "项目执行专家",
        "focus_area": "执行可行性、落地速度",
        "tone": "激进型",
        "is_active": 1
    },
    {
        "id": 5,
        "name": "土·稳健型",
        "role_description": "财务成本专家",
        "focus_area": "成本投入与回报",
        "tone": "保守型",
        "is_active": 1
    }
]

def get_templates() -> List[Dict]:
    """获取启用的模板列表"""
    return [t for t in _templates if t["is_active"] == 1]

def get_all_templates() -> List[Dict]:
    """获取全部模板（管理员用）"""
    return _templates.copy()

def create_template(data: Dict) -> Dict:
    new_id = max((t["id"] for t in _templates), default=0) + 1
    new_template = {
        "id": new_id,
        "name": data["name"],
        "role_description": data.get("role_description", ""),
        "focus_area": data.get("focus_area", ""),
        "tone": data.get("tone", ""),
        "is_active": data.get("is_active", 1)
    }
    _templates.append(new_template)
    return new_template

def update_template(template_id: int, data: Dict) -> Optional[Dict]:
    for t in _templates:
        if t["id"] == template_id:
            t.update(data)
            return t
    return None

def delete_template(template_id: int) -> Dict:
    global _templates
    _templates = [t for t in _templates if t["id"] != template_id]
    return {"message": "删除成功"}

# ---------- 统计与日志 ----------
def get_admin_stats() -> Dict:
    total_tasks = len(_mock_tasks_db)
    completed = sum(1 for t in _mock_tasks_db.values() if t["status"] == "completed")
    return {
        "total_users": len(_mock_users_db),
        "total_tasks": total_tasks,
        "completed_tasks": completed,
        "failed_tasks": total_tasks - completed
    }

_logs = []
_log_counter = 1

def get_admin_logs(event_type: Optional[str] = None, limit: int = 100) -> List[Dict]:
    # 简单模拟几条日志
    global _logs
    if not _logs:
        _logs.append({
            "id": 1,
            "user_id": 1,
            "event_type": "login",
            "description": "管理员登录",
            "created_at": "2026-06-01T00:00:00Z"
        })
    logs = _logs
    if event_type:
        logs = [l for l in logs if l["event_type"] == event_type]
    return logs[-limit:]

# ---------- 管理员需要额外实现的接口 ----------
def get_all_users() -> List[Dict]:
    return [
        {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "created_at": user.get("created_at", "2026-01-01T00:00:00Z")
        }
        for user in _mock_users_db.values()
    ]

def get_all_tasks(limit: int = 100, offset: int = 0) -> List[Dict]:
    tasks = list(_mock_tasks_db.values())
    tasks.sort(key=lambda x: x["created_at"], reverse=True)
    return tasks[offset:offset+limit]