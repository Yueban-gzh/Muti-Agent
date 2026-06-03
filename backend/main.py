"""
FastAPI 应用入口模块
-------------------
项目的启动入口，负责：
- 创建 FastAPI 应用实例
- 配置 CORS 跨域中间件
- 注册所有 API 路由
- 应用启动时自动初始化数据库表
"""

from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.endpoints.auth import router as auth_router
from api.endpoints.tasks import router as tasks_router
from api.endpoints.feedback import router as feedback_router
from api.endpoints.history import router as history_router
from api.endpoints.templates import router as templates_router
from api.endpoints.admin import router as admin_router
from core.config import APP_TITLE, APP_VERSION, DATABASE_URL, LLM_BACKEND
from db.database import engine, Base, AsyncSessionLocal
from db.init_data import seed_default_data

# ============================================================================
# 应用生命周期管理
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 应用生命周期管理器。

    启动时:
        - 自动创建所有数据库表（如果表不存在则创建，已存在则跳过）

    关闭时:
        - 释放数据库引擎连接资源
    """
    # --- 启动阶段：初始化数据库表 ---
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 启用 SQLite WAL 模式以支持更好的并发读写性能
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
    print(f"[启动] 数据库表初始化完成（{DATABASE_URL}）")

    if LLM_BACKEND == "local":
        from ai.llm.local_client import preload_local_model

        print("[启动] 正在预加载本地 LLM 模型（首次约 1~3 分钟）...")
        await asyncio.to_thread(preload_local_model)
        print("[启动] 本地 LLM 模型已就绪")

    # --- 插入默认数据（管理员 + 预设模板） ---
    async with AsyncSessionLocal() as session:
        await seed_default_data(session)

    print(f"[启动] {APP_TITLE} v{APP_VERSION} 已就绪")

    yield  # 应用运行期间在此处挂起

    # --- 关闭阶段：释放资源 ---
    await engine.dispose()
    print("[关闭] 数据库引擎已释放")


# ============================================================================
# FastAPI 应用实例
# ============================================================================

app = FastAPI(
    title=APP_TITLE,
    version=APP_VERSION,
    description="""
## 可配置多智能体决策辅助系统 — 后端 API

### 完整功能：
- **用户认证**：注册、登录、JWT 鉴权
- **决策任务**：创建任务、自定义 Agent 人设、多模式分析
- **AI 分析**：多 Agent 并发调用、语义相似度、冲突检测、综合建议
- **用户反馈**：方案采纳投票、偏好数据收集
- **管理员后台**：反馈统计、系统管理

### 技术栈：
- **FastAPI** 异步 Web 框架
- **SQLAlchemy 2.0** + **aiosqlite** 异步数据库
- **Pydantic V2** 数据校验
- **JWT** + **bcrypt** 安全认证
- **sentence-transformers** 语义相似度
- **httpx** 异步 LLM 调用
""",
    lifespan=lifespan,
    docs_url="/docs",          # Swagger UI 文档地址
    redoc_url="/redoc",        # ReDoc 文档地址
)

# ============================================================================
# CORS 跨域中间件配置
# ============================================================================

# 允许所有来源的跨域请求，方便前端联调
# 生产环境中应限制为具体的前端域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],            # 允许所有来源
    allow_credentials=True,         # 允许携带 Cookie
    allow_methods=["*"],            # 允许所有 HTTP 方法
    allow_headers=["*"],            # 允许所有请求头
)

# ============================================================================
# 路由注册
# ============================================================================


# 认证相关路由（注册、登录、获取当前用户）
app.include_router(auth_router)

# 决策任务相关路由（创建、状态查询、结果获取）
app.include_router(tasks_router)

# 用户反馈相关路由（提交采纳投票、反馈统计）
app.include_router(feedback_router)

# 历史记录与报告导出路由
app.include_router(history_router)

# Agent 模板查询路由
app.include_router(templates_router)

# 管理员后台路由
app.include_router(admin_router)


# ============================================================================
# 根路径：健康检查
# ============================================================================


@app.get("/", tags=["系统"])
async def root():
    """
    根路径 — 健康检查接口。

    返回应用的基本状态信息，可用于确认服务是否正常运行。
    """
    return {
        "message": f"欢迎使用 {APP_TITLE}",
        "version": APP_VERSION,
        "status": "running",
        "docs": "/docs",
    }


# ============================================================================
# 直接运行入口
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    # 使用 uvicorn 启动 ASGI 服务器
    # host="0.0.0.0": 监听所有网络接口（允许局域网访问）
    # port=8000: 默认端口
    # reload=True: 开发模式下代码变更时自动重启
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
