import requests
from typing import Optional, Dict, Any
from PyQt6.QtCore import QThread, pyqtSignal

# ---------- 异步登录线程 ----------
class LoginThread(QThread):
    finished = pyqtSignal(object)  # 发送 (user_info, token)
    error = pyqtSignal(str)

    def __init__(self, base_url: str, username: str, password: str):
        super().__init__()
        self.base_url = base_url
        self.username = username
        self.password = password

    def run(self):
        try:
            # 1. 登录
            resp = requests.post(
                f"{self.base_url}/api/auth/login",
                data={"username": self.username, "password": self.password},
                timeout=10
            )
            if resp.status_code != 200:
                self.error.emit("用户名或密码错误")
                return
            data = resp.json()
            token = data.get("access_token")
            if not token:
                self.error.emit("登录响应缺少 token")
                return

            # 2. 获取用户信息
            headers = {"Authorization": f"Bearer {token}"}
            me_resp = requests.get(
                f"{self.base_url}/api/auth/me",
                headers=headers,
                timeout=10
            )
            if me_resp.status_code != 200:
                self.error.emit("获取用户信息失败")
                return
            user_info = me_resp.json()
            self.finished.emit((user_info, token))
        except Exception as e:
            self.error.emit(str(e))

# ---------- 真实后端 API 客户端（异步登录）----------
class RealAPI:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self._token: Optional[str] = None
        self._current_user: Optional[Dict[str, Any]] = None

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def set_token(self, token: str, user_info: dict):
        self._token = token
        self._current_user = user_info

    # ---------- 异步登录 ----------
    def login_async(self, username: str, password: str, callback, error_callback):
        self._login_thread = LoginThread(self.base_url, username, password)
        self._login_thread.finished.connect(callback)
        self._login_thread.error.connect(error_callback)
        self._login_thread.start()

    # ---------- 同步方法（保留，但建议不用）----------
    def login(self, username: str, password: str) -> Optional[dict]:
        # 同步方法会卡界面，仅用于测试
        resp = requests.post(
            f"{self.base_url}/api/auth/login",
            data={"username": username, "password": password}
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        self._token = data.get("access_token")
        me_resp = requests.get(
            f"{self.base_url}/api/auth/me",
            headers=self._headers()
        )
        if me_resp.status_code == 200:
            self._current_user = me_resp.json()
        return data

    def get_current_user(self) -> Optional[dict]:
        return self._current_user

    # ---------- 注册（同步，不影响主体验）----------
    def register(self, username: str, password: str, email: str = "") -> dict:
        resp = requests.post(
            f"{self.base_url}/api/auth/register",
            json={"username": username, "password": password},
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json()
        return {"message": resp.text}

    # ---------- 任务（同步，但可后续改为异步）----------
    def start_debate(self, payload: dict) -> Optional[dict]:
        resp = requests.post(
            f"{self.base_url}/api/tasks/create",
            json=payload,
            headers=self._headers(),
            timeout=30
        )
        if resp.status_code in (200, 201):
            return resp.json()
        return None

    def get_debate_status(self, task_id: int) -> Optional[str]:
        try:
            resp = requests.get(
                f"{self.base_url}/api/tasks/{task_id}/status",
                headers=self._headers(),
                timeout=60 # 增加超时时间到60秒
            )
            if resp.status_code == 200:
                return resp.json().get("status")
        except requests.exceptions.Timeout:
            print(f"获取任务 {task_id} 状态超时，继续等待")
            return None   # 超时返回 None，表示未知状态
        return None

    def get_debate_result(self, task_id: int) -> Optional[dict]:
        resp = requests.get(
            f"{self.base_url}/api/tasks/{task_id}/result",
            headers=self._headers(),
            timeout=30
        )
        if resp.status_code == 200:
            return resp.json()
        return None
    def get_messages(self, task_id: int) -> list:
        """获取讨论消息列表"""
        resp = requests.get(
            f"{self.base_url}/api/tasks/{task_id}/messages",
            headers=self._headers()
        )
        if resp.status_code == 200:
            return resp.json()
        return []

    def send_message(self, task_id: int, content: str, reply_scope: str) -> bool:
        """发送用户消息并触发Agent回复"""
        payload = {"content": content, "reply_scope": reply_scope}
        resp = requests.post(
            f"{self.base_url}/api/tasks/{task_id}/messages",
            json=payload,
            headers=self._headers()
        )
        return resp.status_code in (200, 201)

    def agent_exchange(self, task_id: int) -> bool:
        """辩论模式下，让辩手自主交锋一轮"""
        resp = requests.post(
            f"{self.base_url}/api/tasks/{task_id}/debate/agent-exchange",
            headers=self._headers()
        )
        return resp.status_code in (200, 201)

    def finalize_task(self, task_id: int) -> dict:
        """结束讨论，生成正式报告"""
        resp = requests.post(
            f"{self.base_url}/api/tasks/{task_id}/finalize",
            headers=self._headers()
        )
        if resp.status_code in (200, 201):
            return resp.json()
        return None

    # ---------- 反馈 ----------
    def submit_feedback(self, task_id: int, chosen_type: str,
                        chosen_agent_id: Optional[int] = None,
                        comment: str = "") -> Optional[dict]:
        payload = {"task_id": task_id, "chosen_type": chosen_type, "comment": comment}
        if chosen_agent_id is not None:
            payload["chosen_agent_id"] = chosen_agent_id
        resp = requests.post(
            f"{self.base_url}/api/feedback/vote",
            json=payload,
            headers=self._headers(),
            timeout=10
        )
        if resp.status_code in (200, 201):
            return resp.json()
        return None

    # ---------- 历史 ----------
    def get_my_history(self) -> list:
        resp = requests.get(
            f"{self.base_url}/api/history/",
            headers=self._headers(),
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json()
        return []

    def export_report(self, task_id: int) -> Optional[str]:
        resp = requests.get(
            f"{self.base_url}/api/history/{task_id}/export",
            headers=self._headers(),
            timeout=15
        )
        if resp.status_code == 200:
            return resp.text
        return None

    # ---------- 模板 ----------
    def list_templates(self, include_inactive: bool = False) -> dict:
        endpoint = "/api/templates/all" if include_inactive else "/api/templates/"
        resp = requests.get(
            f"{self.base_url}{endpoint}",
            headers=self._headers()
        )
        if resp.status_code == 200:
            return resp.json()   # 直接返回字典，不要只取 .get("templates")
        return {"templates": [], "total": 0}
    def list_all_templates(self) -> list:
        return self.list_templates(include_inactive=True)["templates"]

    # ---------- 管理员后台 ----------
    def get_all_users(self) -> list:
        resp = requests.get(
            f"{self.base_url}/api/admin/users",
            headers=self._headers(),
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json()
        return []

    def get_all_tasks(self, limit: int = 100, offset: int = 0) -> list:
        resp = requests.get(
            f"{self.base_url}/api/admin/tasks",
            params={"limit": limit, "offset": offset},
            headers=self._headers(),
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json()
        return []

    def get_admin_stats(self) -> dict:
        resp = requests.get(
            f"{self.base_url}/api/admin/stats",
            headers=self._headers(),
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json()
        return {}

    def create_template(self, data: dict) -> dict:
        resp = requests.post(
            f"{self.base_url}/api/admin/templates",
            json=data,
            headers=self._headers(),
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json()
        return {"success": False, "message": resp.text}

    def update_template(self, template_id: int, data: dict) -> dict:
        resp = requests.put(
            f"{self.base_url}/api/admin/templates/{template_id}",
            json=data,
            headers=self._headers(),
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json()
        return {"success": False, "message": resp.text}

    def delete_template(self, template_id: int) -> bool:
        resp = requests.delete(
            f"{self.base_url}/api/admin/templates/{template_id}",
            headers=self._headers(),
            timeout=10
        )
        return resp.status_code == 200

    def get_admin_logs(self, event_type: str = None, limit: int = 100) -> list:
        params = {"limit": limit}
        if event_type:
            params["event_type"] = event_type
        resp = requests.get(
            f"{self.base_url}/api/admin/logs",
            params=params,
            headers=self._headers(),
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json()
        return []
    
    def logout(self) -> bool:
        """退出登录，清除本地 token 和用户信息"""
        self._token = None
        self._current_user = None
        return True