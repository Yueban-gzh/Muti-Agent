"""
应用运行日志配置
----------------
将 Python logging 同时输出到终端与 logs/app.log（按大小轮转）。
与 operation_logs（业务审计）互补：后者记录关键业务事件，本模块记录调试与异常堆栈。
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from core.config import (
    BASE_DIR,
    LOG_DIR,
    LOG_FILE_BACKUP_COUNT,
    LOG_FILE_MAX_MB,
    LOG_LEVEL,
    PROJECT_ROOT,
)

_CONFIGURED = False

_DEFAULT_LOG_DIR = Path(PROJECT_ROOT) / "logs"
_DEFAULT_LOG_FILE = _DEFAULT_LOG_DIR / "app.log"


def setup_logging(
    *,
    log_dir: Path | None = None,
    level: int | None = None,
    max_bytes: int | None = None,
    backup_count: int | None = None,
) -> Path:
    """
    初始化全局 logging（幂等，重复调用无副作用）。

    返回实际日志文件路径。
    """
    global _CONFIGURED
    log_directory = log_dir or Path(LOG_DIR)
    log_file = log_directory / "app.log"
    if _CONFIGURED:
        return log_file

    log_directory.mkdir(parents=True, exist_ok=True)

    resolved_level = level if level is not None else getattr(
        logging, LOG_LEVEL, logging.INFO
    )
    resolved_max_bytes = (
        max_bytes if max_bytes is not None else LOG_FILE_MAX_MB * 1024 * 1024
    )
    resolved_backup = (
        backup_count if backup_count is not None else LOG_FILE_BACKUP_COUNT
    )

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=resolved_max_bytes,
        backupCount=resolved_backup,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(resolved_level)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(resolved_level)

    root = logging.getLogger()
    root.setLevel(resolved_level)
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # 降低第三方库噪音
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("transformers").setLevel(logging.WARNING)

    _CONFIGURED = True
    logging.getLogger("app").info(
        "运行日志已启用: 文件=%s backend=%s",
        log_file,
        BASE_DIR,
    )
    return log_file
