import time
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any

# 模拟用户数据库
_mock_users_db: Dict[str, Dict[str, Any]] = {
    "admin": {
        "id": 1,
        "username": "admin",
        "password": "admin123456",
        "role": "admin",
        "created_at": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    },
    "user": {
        "id": 2,
        "username": "user",
        "password": "123456",
        "role": "user",
        "created_at": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    }
}
_mock_tokens: Dict[str, Dict[str, Any]] = {}
_next_id = 3

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

def register(username: str, password: str) -> Optional[Dict[str, Any]]:
    """注册用户，成功返回 UserResponse，失败返回 None（前端根据返回值判断）"""
    global _next_id
    if username in _mock_users_db:
        return None  # 用户名已存在
    new_id = _next_id
    _next_id += 1
    user = {
        "id": new_id,
        "username": username,
        "password": password,
        "role": "user",
        "created_at": _utcnow_iso()
    }
    _mock_users_db[username] = user
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "created_at": user["created_at"]
    }

def login(username: str, password: str) -> Optional[Dict[str, Any]]:
    """登录成功返回 Token，失败返回 None"""
    user = _mock_users_db.get(username)
    if not user or user["password"] != password:
        return None
    token = f"mock_jwt_{uuid.uuid4().hex}"
    _mock_tokens[token] = user
    return {
        "access_token": token,
        "token_type": "bearer"
    }

def get_current_user(token: str) -> Optional[Dict[str, Any]]:
    """根据 token 返回用户信息（不含密码）"""
    user = _mock_tokens.get(token)
    if not user:
        return None
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "created_at": user["created_at"]
    }