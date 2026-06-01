from typing import Optional
from .auth import register, login, get_current_user
from .debate import create_task, get_task_status, get_task_result
from .feedback import submit_feedback, get_feedback_stats
from .history import get_history, export_report
from .admin import (
    get_all_templates, get_templates,
    create_template, update_template, delete_template,
    get_admin_stats, get_admin_logs,
    get_all_users, get_all_tasks
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

    # 认证
    def register(self, username: str, password: str) -> dict:
        return register(username, password)

    def login(self, username: str, password: str) -> Optional[dict]:
        result = login(username, password)
        if result:
            self.set_token(result["access_token"])
        return result

    def logout(self) -> bool:
        self._token = None
        self._current_user = None
        return True

    # 任务
    def start_debate(self, payload: dict) -> Optional[dict]:
        if not self._current_user:
            return None
        return create_task(payload, self._current_user["id"])

    def get_debate_status(self, task_id: int) -> Optional[str]:
        r = get_task_status(task_id)
        return r["status"] if r else None

    def get_debate_result(self, task_id: int) -> Optional[dict]:
        return get_task_result(task_id)

    # 反馈
    def submit_feedback(self, task_id: int, chosen_type: str, chosen_agent_id: int = None, comment: str = "") -> Optional[dict]:
        if not self._current_user:
            return None
        data = {
            "task_id": task_id,
            "chosen_type": chosen_type,
            "comment": comment
        }
        if chosen_agent_id is not None:
            data["chosen_agent_id"] = chosen_agent_id
        return submit_feedback(data)

    def get_feedback_stats(self) -> dict:
        return get_feedback_stats()

    # 历史
    def get_my_history(self) -> list:
        if not self._current_user:
            return []
        return get_history(self._current_user["id"])

    def export_report(self, task_id: int) -> str:
        return export_report(task_id)

    # 模板（用户）
    def list_templates(self) -> list:
        return get_templates()

    def list_all_templates(self) -> list:
        return get_all_templates()

    # 模板（管理员）
    def create_template(self, data: dict) -> dict:
        return create_template(data)

    def update_template(self, template_id: int, data: dict) -> Optional[dict]:
        return update_template(template_id, data)

    def delete_template(self, template_id: int) -> dict:
        return delete_template(template_id)

    # 管理员后台
    def get_all_users(self) -> list:
        if not self._current_user or self._current_user.get("role") != "admin":
            return []
        return get_all_users()

    def get_all_tasks(self, limit=100, offset=0) -> list:
        if not self._current_user or self._current_user.get("role") != "admin":
            return []
        return get_all_tasks(limit, offset)

    def get_admin_stats(self) -> dict:
        if not self._current_user or self._current_user.get("role") != "admin":
            return {}
        return get_admin_stats()

    def get_admin_logs(self, event_type=None, limit=100) -> list:
        if not self._current_user or self._current_user.get("role") != "admin":
            return []
        return get_admin_logs(event_type, limit)