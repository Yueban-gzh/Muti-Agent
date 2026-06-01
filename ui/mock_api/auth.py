import time
from typing import Optional, Dict, Any

_mock_users_db = {
    "admin": {
        "id": 1,
        "username": "admin",
        "password": "123456",
        "role": "admin"
    },
    "user": {
        "id": 2,
        "username": "user",
        "password": "123456",
        "role": "user"
    }
}

_mock_tokens: Dict[str, Dict] = {}

def register(username: str, password: str) -> Dict[str, Any]:
    if username in _mock_users_db:
        # 模拟失败（实际应返回 HTTP 400）
        return {"message": "用户名已存在"}
    user_id = len(_mock_users_db) + 1
    _mock_users_db[username] = {
        "id": user_id,
        "username": username,
        "password": password,
        "role": "user"
    }
    return {"message": "注册成功"}

def login(username: str, password: str) -> Optional[Dict[str, Any]]:
    user = _mock_users_db.get(username)
    if not user or user["password"] != password:
        return None  # 模拟认证失败
    token = f"mock-jwt-token-{user['id']}-{int(time.time())}"
    _mock_tokens[token] = user
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"]
        }
    }

def get_current_user(token: str) -> Optional[Dict[str, Any]]:
    return _mock_tokens.get(token)