"""
数据库连接与会话管理模块
------------------------
负责创建异步数据库引擎、会话工厂、声明式基类，
并提供 FastAPI 依赖注入使用的数据库会话生成器。
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from core.config import DATABASE_URL

# ============================================================================
# 异步数据库引擎
# ============================================================================

# 创建异步 SQLAlchemy 引擎
# echo=False: 不打印 SQL 日志（开发调试时可设为 True）
# connect_args: SQLite 需要 check_same_thread=False 以支持多线程访问
# pool_pre_ping: 连接前检查连接是否有效
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)

# ============================================================================
# 异步会话工厂
# ============================================================================

# 创建异步会话工厂，绑定到上面的引擎
# expire_on_commit=False: 提交后不过期对象属性，避免后续访问触发懒加载异常
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ============================================================================
# 声明式基类
# ============================================================================


class Base(DeclarativeBase):
    """
    SQLAlchemy 声明式基类。
    所有数据表模型类继承自此基类，以便统一管理元数据。
    """
    pass


# ============================================================================
# FastAPI 依赖注入：获取数据库会话
# ============================================================================


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    为每个 HTTP 请求提供独立的数据库会话。

    使用方式（在 FastAPI 路由中）:
        @router.get("/some-path")
        async def some_handler(db: AsyncSession = Depends(get_db)):
            ...

    该函数会在请求开始时创建会话，请求结束后自动关闭会话，
    确保连接资源不会泄漏。
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
