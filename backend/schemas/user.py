"""
用户相关 Pydantic Schema 定义
-----------------------------
使用 Pydantic V2 定义请求校验和响应序列化模型。
所有与用户相关的数据传输对象（DTO）集中在此模块定义。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# 请求模型（接收客户端提交的数据）
# ============================================================================


class UserCreate(BaseModel):
    """
    用户注册请求体

    用于 POST /api/auth/register 接口，接收用户名和密码。
    包含字段级别的长度和内容校验。
    """

    # 用户名：2~50 个字符，不能为空
    username: str = Field(
        ...,
        min_length=2,
        max_length=50,
        description="用户名，2~50 个字符",
        examples=["zhangsan"],
    )

    # 密码：6~128 个字符，不能为空
    password: str = Field(
        ...,
        min_length=6,
        max_length=128,
        description="密码，至少 6 个字符",
        examples=["SecurePass123!"],
    )


class UserLogin(BaseModel):
    """
    用户登录请求体（JSON 格式备选）

    用于期望 JSON 格式的场景。默认推荐使用 OAuth2PasswordRequestForm，
    该表单类由 FastAPI 内置提供，兼容标准 OAuth2 流程。
    """

    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


# ============================================================================
# 响应模型（返回给客户端的数据，已剔除敏感字段）
# ============================================================================


class UserResponse(BaseModel):
    """
    用户信息响应体

    返回用户的基本信息，明确排除 password_hash 字段，
    确保密码哈希不会通过 API 泄露。
    """

    id: int = Field(..., description="用户 ID")
    username: str = Field(..., description="用户名")
    role: str = Field(..., description="用户角色（user / admin）")
    created_at: datetime = Field(..., description="账号创建时间")

    # Pydantic V2 配置：允许从 ORM 对象属性自动映射
    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    """
    JWT Token 响应体

    用于 POST /api/auth/login 接口的返回值，
    包含 access_token 和 token_type。
    """

    access_token: str = Field(..., description="JWT Access Token 字符串")
    token_type: str = Field(default="bearer", description="Token 类型，固定为 bearer")


class MessageResponse(BaseModel):
    """
    通用消息响应体

    用于只需要返回一条消息的接口（如操作成功提示）。
    """

    message: str = Field(..., description="响应消息")
