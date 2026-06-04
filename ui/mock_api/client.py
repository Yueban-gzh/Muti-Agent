from typing import Dict, Any, Optional, List
from .auth import register, login, get_current_user
from .debate import create_task, get_task_status, get_task_result
from .feedback import submit_feedback, get_feedback_stats
from .history import get_user_history, export_report
from .admin import (
    get_all_users, get_all_tasks, get_admin_stats,
    get_templates, create_template, update_template, delete_template,
    get_logs
)

class MockAPI:
    def __init__(self):
        self._token: Optional[str] = None
        self._current_user: Optional[dict] = None

    def set_token(self, token: str):
        self._token = token
        self._current_user = get_current_user(token)

    def get_current_user(self) -> Optional[dict]:
        return self._current_user

    def register(self, username: str, password: str, email: str = "") -> dict:
        result = register(username, password)
        if result:
            return result
        return {"message": "用户名已存在"}   # 兼容前端检查

    def login(self, username: str, password: str) -> Optional[dict]:
        result = login(username, password)
        if result:
            self.set_token(result["access_token"])
        return result

    def logout(self) -> bool:
        self._token = None
        self._current_user = None
        return True

    def start_debate(self, payload: dict) -> Optional[dict]:
        if not self._current_user:
            return None
        return create_task(payload, self._current_user["id"])

    def get_debate_status(self, task_id: int) -> Optional[str]:
        r = get_task_status(task_id)
        return r["status"] if r else None

    def get_debate_result(self, task_id: int) -> Optional[dict]:
        return get_task_result(task_id)

    def submit_feedback(self, task_id: int, chosen_type: str, chosen_agent_id: int = None, comment: str = "") -> Optional[dict]:
        if not self._current_user:
            return None
        return submit_feedback(task_id, self._current_user["id"], chosen_type, chosen_agent_id, comment)

    def get_feedback_stats(self) -> dict:
        return get_feedback_stats()

    def get_my_history(self) -> list:
        if not self._current_user:
            return []
        return get_user_history(self._current_user["id"])

    def export_report(self, task_id: int) -> str:
        return export_report(task_id)

    def list_templates(self, include_inactive: bool = False) -> list:
        return get_templates(include_inactive)

    def list_all_templates(self) -> list:
        return get_templates(include_inactive=True)

    def create_template(self, data: dict) -> dict:
        return create_template(data)

    def update_template(self, template_id: int, data: dict) -> dict:
        result = update_template(template_id, data)
        if result:
            return result
        return {"success": False, "message": "模板不存在"}

    def delete_template(self, template_id: int) -> bool:
        return delete_template(template_id)

    def get_all_users(self) -> list:
        return get_all_users()

    def get_all_tasks(self, limit=100, offset=0) -> list:
        return get_all_tasks(limit, offset)

    def get_admin_stats(self) -> dict:
        return get_admin_stats()

    def get_admin_logs(self, event_type=None, limit=100) -> list:
        return get_logs(event_type, limit)
    def get_messages(self, task_id: int) -> list:
        from .debate import get_messages
        return get_messages(task_id)

    def send_message(self, task_id: int, content: str, reply_scope: str) -> bool:
        if not self._current_user:
            return False
        from .debate import send_message
        result = send_message(task_id, self._current_user["id"], content, reply_scope)
        return result.get("status") == "ok"

    def agent_exchange(self, task_id: int) -> bool:
        if not self._current_user:
            return False
        from .debate import agent_exchange
        result = agent_exchange(task_id)
        return result.get("status") == "ok"

    def finalize_task(self, task_id: int) -> dict:
        if not self._current_user:
            return None
        from .debate import finalize_task
        return finalize_task(task_id)
    def get_admin_stats(self) -> Dict[str, Any]:
        return {
            "total_users": 8,
            "total_tasks": 25,
            "completed_tasks": 20,
            "failed_tasks": 1,
            "pending_tasks": 4,
            "task_queue_depth": 2,
            "pipeline_active": 1,
            "pipeline_max": 3,
            "llm_active": 1,
            "llm_max": 2,
            "llm_available_slots": 1,
            "total_feedback": 15,
            "active_templates": 5
        }
