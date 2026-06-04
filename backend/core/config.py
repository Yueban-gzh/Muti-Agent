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

# ============================================================================
# 并发控制（任务队列 + 全局 LLM 槽位）
# ============================================================================

# 全局 LLM 槽位（Agent + 综合建议 + local/api 共用）
LLM_MAX_CONCURRENT: int = int(os.getenv("LLM_MAX_CONCURRENT", "2"))

# 兼容旧配置名
_legacy_local = os.getenv("LOCAL_MAX_CONCURRENT")
if _legacy_local and not os.getenv("LLM_MAX_CONCURRENT"):
    LLM_MAX_CONCURRENT = int(_legacy_local)

# 同时执行的完整流水线数
MAX_CONCURRENT_PIPELINES: int = int(os.getenv("MAX_CONCURRENT_PIPELINES", "3"))

# 任务队列上限，0 = 不限制
TASK_QUEUE_MAX_DEPTH: int = int(os.getenv("TASK_QUEUE_MAX_DEPTH", "0"))

# LOCAL_MAX_CONCURRENT 保留为别名，供旧文档引用
LOCAL_MAX_CONCURRENT: int = LLM_MAX_CONCURRENT

# ============================================================================
# 运行日志（文件持久化，见 core/logging_config.py）
# ============================================================================

LOG_DIR: str = os.getenv("LOG_DIR", os.path.join(PROJECT_ROOT, "logs")).replace("\\", "/")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE_MAX_MB: int = int(os.getenv("LOG_FILE_MAX_MB", "10"))
LOG_FILE_BACKUP_COUNT: int = int(os.getenv("LOG_FILE_BACKUP_COUNT", "5"))

# ============================================================================
# 讨论期 → 收束期
# ============================================================================

MAX_DISCUSSION_USER_TURNS: int = int(os.getenv("MAX_DISCUSSION_USER_TURNS", "30"))
MAX_USER_MESSAGE_CHARS: int = int(os.getenv("MAX_USER_MESSAGE_CHARS", "500"))
DISCUSS_MAX_NEW_TOKENS: int = int(os.getenv("DISCUSS_MAX_NEW_TOKENS", "512"))
DISCUSS_HISTORY_MAX_MESSAGES: int = int(os.getenv("DISCUSS_HISTORY_MAX_MESSAGES", "12"))

DISCUSSION_SUMMARY_TARGET_CHARS: int = int(os.getenv("DISCUSSION_SUMMARY_TARGET_CHARS", "800"))
DISCUSSION_SUMMARY_MAX_NEW_TOKENS: int = int(os.getenv("DISCUSSION_SUMMARY_MAX_NEW_TOKENS", "1024"))
DISCUSS_INPUT_MAX_CHARS: int = int(os.getenv("DISCUSS_INPUT_MAX_CHARS", "12000"))
SUMMARY_LLM_TEMPERATURE: float = float(os.getenv("SUMMARY_LLM_TEMPERATURE", "0.3"))

DEBATE_REQUIRE_PRO_CON: bool = os.getenv("DEBATE_REQUIRE_PRO_CON", "1").strip() in ("1", "true", "yes")
DEBATE_MAX_JUDGE: int = int(os.getenv("DEBATE_MAX_JUDGE", "1"))
MAX_DEBATE_EXCHANGE_ROUNDS: int = int(os.getenv("MAX_DEBATE_EXCHANGE_ROUNDS", "15"))

# 创建任务后自动跑旧版一次性流水线（兼容 CLI 联调）
LEGACY_AUTO_FINALIZE: bool = os.getenv("LEGACY_AUTO_FINALIZE", "0").strip() in ("1", "true", "yes")
