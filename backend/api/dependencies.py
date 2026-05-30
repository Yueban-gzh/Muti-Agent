"""
API 依赖项模块
-------------
定义 FastAPI 路由中常用的依赖注入函数，
包括获取当前登录用户、校验管理员权限等。
这些依赖项可直接通过 Depends() 在路由中使用。
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import SECRET_KEY, ALGORITHM
from db.database import get_db
from db.models import User

# ============================================================================
# OAuth2 方案配置
# ============================================================================

# 指定登录接口的 URL，用于 OAuth2 流程中的 Token 获取
# FastAPI 自动生成的文档中，"Authorize" 按钮会引导用户到此接口获取 Token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# 认证失败时的统一异常响应
credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="无法验证身份，请重新登录",
    headers={"WWW-Authenticate": "Bearer"},
)

# 权限不足时的统一异常响应
forbidden_exception = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="权限不足，需要管理员权限",
)


# ============================================================================
# 获取当前登录用户
# ============================================================================


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    从请求的 Authorization 头中提取并验证 JWT Token，
    返回对应的 User 数据库对象。

    使用方式:
        @router.get("/api/protected")
        async def protected_route(current_user: User = Depends(get_current_user)):
            ...

    参数:
        token: 从 Authorization: Bearer <token> 头中自动提取的 JWT
        db: 通过依赖注入获取的异步数据库会话

    返回:
        User: 当前登录用户的 ORM 模型对象

    异常:
        401 UNAUTHORIZED: Token 无效或已过期，或用户不存在
    """
    # 1. 解码并验证 JWT Token
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exception
    except InvalidTokenError:
        raise credentials_exception

    # 2. 从数据库中查找用户
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    return user


# ============================================================================
# 获取当前管理员用户（在校验登录的基础上额外校验角色）
# ============================================================================


async def get_current_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    校验当前登录用户是否具有管理员权限。

    此依赖项必须在 get_current_user 之后调用，
    即先通过 JWT 认证，再检查角色。

    使用方式:
        @router.get("/api/admin/xxx")
        async def admin_route(admin: User = Depends(get_current_admin)):
            ...

    参数:
        current_user: 由 get_current_user 依赖注入的当前用户

    返回:
        User: 具有 admin 角色的用户对象

    异常:
        403 FORBIDDEN: 当前用户角色不是 admin
    """
    if current_user.role != "admin":
        raise forbidden_exception
    return current_user
