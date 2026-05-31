"""
安全工具模块
-----------
提供密码哈希、密码校验、JWT Token 生成与解析等安全相关工具函数。
所有与认证、加密相关的逻辑集中在此模块中，便于统一维护和审计。
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from passlib.context import CryptContext

from core.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, BCRYPT_ROUNDS

# ============================================================================
# 密码加密上下文
# ============================================================================

# 使用 bcrypt 算法进行密码哈希，设置加密轮数
# deprecated="auto" 表示当算法被标记为过时时自动升级
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=BCRYPT_ROUNDS,
)


def get_password_hash(password: str) -> str:
    """
    对明文密码进行 bcrypt 哈希处理。

    参数:
        password: 用户输入的明文密码

    返回:
        str: bcrypt 哈希后的密码字符串，可直接存入数据库
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    校验明文密码与数据库中的哈希密码是否匹配。

    参数:
        plain_password: 用户登录时输入的明文密码
        hashed_password: 数据库中存储的 bcrypt 哈希密码

    返回:
        bool: 匹配返回 True，否则返回 False
    """
    return pwd_context.verify(plain_password, hashed_password)


# ============================================================================
# JWT Token 工具函数
# ============================================================================

def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    生成 JWT Access Token。

    参数:
        data: 要编码到 Token 载荷中的数据（如 {"sub": username, "role": "user"}）
        expires_delta: 自定义过期时间，若未指定则使用配置文件中的默认值

    返回:
        str: 编码后的 JWT Token 字符串
    """
    # 复制一份数据，避免修改原始 dict
    to_encode = data.copy()

    # 计算过期时间（使用 UTC 时间）
    if expires_delta is not None:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    # 将过期时间加入载荷
    to_encode.update({"exp": expire})

    # 使用 HS256 算法编码
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """
    解析并验证 JWT Access Token，返回载荷数据。

    参数:
        token: JWT Token 字符串

    返回:
        dict: Token 载荷中的数据

    异常:
        jwt.ExpiredSignatureError: Token 已过期
        jwt.InvalidTokenError: Token 无效（签名错误、格式错误等）
    """
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    return payload
