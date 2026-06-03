"""
全局配置模块
-----------
集中管理项目的所有配置常量，包括 JWT 密钥、算法、Token 过期时间、
数据库连接 URL 等。任何模块需要配置时统一从此处导入。
"""

import os
from pathlib import Path

# ============================================================================
# 环境变量加载（从项目根目录的 os.env 文件读取 API Key）
# ============================================================================

# os.env 文件的绝对路径
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / "os.env"

if _ENV_FILE.exists():
    with open(_ENV_FILE, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            # 跳过空行和注释行
            if not _line or _line.startswith("#"):
                continue
            if "=" in _line:
                _key, _value = _line.split("=", 1)
                _key = _key.strip()
                _value = _value.strip().strip('"').strip("'")
                os.environ.setdefault(_key, _value)

# ============================================================================
# JWT 鉴权配置
# ============================================================================

# JWT 签名密钥（生产环境应通过环境变量注入，此处为开发默认值）
SECRET_KEY: str = os.getenv("SECRET_KEY", "jixia-multi-agent-decision-secret-key-2025")

# JWT 签名算法（HS256 为对称加密，适合单服务架构）
ALGORITHM: str = "HS256"

# Access Token 默认过期时间（分钟），默认 60 分钟
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# ============================================================================
# 数据库配置
# ============================================================================

# backend/ 目录（数据库等）
BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 项目根目录 muti-agent/（模型权重、os.env）
PROJECT_ROOT: str = os.path.dirname(BASE_DIR)

# SQLite 异步数据库连接 URL
# 使用 aiosqlite 作为异步驱动，数据库文件存储在 backend/ 目录下
# 注意：Windows 路径中的反斜杠必须转换为正斜杠，否则 SQLAlchemy URL 解析会失败
_db_path: str = os.path.join(BASE_DIR, "app.db").replace("\\", "/")
DATABASE_URL: str = f"sqlite+aiosqlite:///{_db_path}"

# ============================================================================
# 密码加密配置
# ============================================================================

# bcrypt 加密轮数（越高越安全但越慢，12 是安全与性能的平衡值）
BCRYPT_ROUNDS: int = 12

# ============================================================================
# 应用配置
# ============================================================================

# 应用标题（显示在 FastAPI 自动生成的文档中）
APP_TITLE: str = "可配置多智能体决策辅助系统"

# 应用版本
APP_VERSION: str = "1.0.0"

# ============================================================================
# DeepSeek API 配置（大模型调用）
# ============================================================================

# API Key（从 os.env 文件加载，若未找到则尝试从系统环境变量获取）
DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")

# DeepSeek API 基础地址（兼容 OpenAI SDK 格式，已包含 /v1 路径）
# 示例：https://www.sophnet.com/api/open-apis/v1
DEEPSEEK_BASE_URL: str = os.getenv(
    "DEEPSEEK_BASE_URL",
    "https://www.sophnet.com/api/open-apis/v1",
)

# 模型名称（注意大小写，需与服务端支持的名称一致）
DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "DeepSeek-V4-Flash")

# API 请求超时时间（秒）
DEEPSEEK_TIMEOUT: int = int(os.getenv("DEEPSEEK_TIMEOUT", "120"))

# 最大重试次数
DEEPSEEK_MAX_RETRIES: int = int(os.getenv("DEEPSEEK_MAX_RETRIES", "2"))

# ============================================================================
# 本地 LLM 配置（课程要求：本地开源模型推理）
# ============================================================================

# llm 后端：local（本地 Qwen）| api（DeepSeek，仅开发备用）
LLM_BACKEND: str = os.getenv("LLM_BACKEND", "local").strip().lower()

_default_model_path = os.path.join(
    PROJECT_ROOT, "models", "Qwen2.5-3B-Instruct"
).replace("\\", "/")

LOCAL_MODEL_PATH: str = os.getenv("LOCAL_MODEL_PATH", _default_model_path)
LOCAL_MAX_NEW_TOKENS: int = int(os.getenv("LOCAL_MAX_NEW_TOKENS", "2048"))
LOCAL_TEMPERATURE: float = float(os.getenv("LOCAL_TEMPERATURE", "0.7"))
# 同时进行的本地生成数（3090 上 2 路较稳）
LOCAL_MAX_CONCURRENT: int = int(os.getenv("LOCAL_MAX_CONCURRENT", "2"))
