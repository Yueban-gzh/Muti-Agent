"""
认证接口模块
-----------
提供用户注册、登录以及获取当前用户信息的 RESTful API 接口。
所有接口统一挂载在 /api/auth 路由前缀下。

接口列表:
    POST /api/auth/register  - 用户注册
    POST /api/auth/login     - 用户登录（获取 JWT Token）
    GET  /api/auth/me        - 获取当前登录用户信息
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user
from core.security import get_password_hash, verify_password, create_access_token
from db.database import get_db
from db.models import User
from schemas.user import UserCreate, UserResponse, Token

# ============================================================================
# 路由初始化
# ============================================================================

# 创建 APIRouter 实例，所有路由以 /api/auth 为前缀
# tags=["认证"] 使这些接口在 FastAPI 自动文档中分组显示
router = APIRouter(prefix="/api/auth", tags=["认证"])


# ============================================================================
# POST /api/auth/register — 用户注册
# ============================================================================


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="用户注册",
    description="使用用户名和密码创建新账号。用户名全局唯一，密码至少 6 个字符。",
)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """
    用户注册接口

    处理流程:
        1. 校验用户名是否已存在
        2. 对密码进行 bcrypt 哈希
        3. 将新用户写入数据库
        4. 返回用户信息（不含密码哈希）

    参数:
        user_data: 包含 username 和 password 的请求体（Pydantic 自动校验）
        db: 异步数据库会话

    返回:
        UserResponse: 包含 id, username, role, created_at

    异常:
        400 BAD REQUEST: 用户名已存在
    """
    # --- 第 1 步：检查用户名是否已被占用 ---
    result = await db.execute(
        select(User).where(User.username == user_data.username)
    )
    existing_user = result.scalar_one_or_none()

    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在",
        )

    # --- 第 2 步：创建新用户（密码哈希后存储） ---
    hashed_password = get_password_hash(user_data.password)

    new_user = User(
        username=user_data.username,
        password_hash=hashed_password,
        role="user",  # 默认注册为普通用户
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)  # 刷新以获取自动生成的 id 和 created_at

    # --- 第 3 步：返回用户信息 ---
    return UserResponse.model_validate(new_user)


# ============================================================================
# POST /api/auth/login — 用户登录
# ============================================================================


@router.post(
    "/login",
    response_model=Token,
    summary="用户登录",
    description="使用用户名和密码登录，成功返回 JWT Access Token。",
)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    用户登录接口

    处理流程:
        1. 根据用户名查找用户
        2. 校验密码是否正确
        3. 生成 JWT Access Token
        4. 返回 Token

    参数:
        form_data: OAuth2 密码表单（包含 username, password, grant_type 等字段）
                   前端可使用 application/x-www-form-urlencoded 格式提交
        db: 异步数据库会话

    返回:
        dict: {"access_token": "xxx", "token_type": "bearer"}

    异常:
        401 UNAUTHORIZED: 账号或密码错误
    """
    # --- 第 1 步：查找用户 ---
    result = await db.execute(
        select(User).where(User.username == form_data.username)
    )
    user = result.scalar_one_or_none()

    # --- 第 2 步：校验用户是否存在以及密码是否正确 ---
    # 统一返回"账号或密码错误"，避免泄露用户是否存在的信息（防枚举攻击）
    if user is None or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # --- 第 3 步：生成 JWT Token ---
    # 载荷中包含用户名和角色信息，供后续权限校验使用
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role}
    )

    # --- 第 4 步：返回 Token ---
    return {"access_token": access_token, "token_type": "bearer"}


# ============================================================================
# GET /api/auth/me — 获取当前用户信息
# ============================================================================


@router.get(
    "/me",
    response_model=UserResponse,
    summary="获取当前用户信息",
    description="根据请求头中的 JWT Token 返回当前登录用户的详细信息。",
)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """
    获取当前登录用户信息

    此接口受 JWT 保护，需要在请求头中携带有效的 Access Token:
        Authorization: Bearer <你的Token>

    参数:
        current_user: 由 get_current_user 依赖项注入的用户对象

    返回:
        UserResponse: 当前用户的 id, username, role, created_at
    """
    return UserResponse.model_validate(current_user)
