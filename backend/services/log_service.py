"""操作日志写入服务。"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from db.database import AsyncSessionLocal
from db.models import OperationLog

logger = logging.getLogger("log_service")

_MAX_DESC_LEN = 2000


async def append_log(
    event_type: str,
    description: str,
    *,
    user_id: Optional[int] = None,
    db: Optional[AsyncSession] = None,
) -> None:
    """
    写入一条操作日志。

    - 传入 db：只 add + flush，由调用方 commit（适合与业务同事务）
    - 不传 db：独立会话立即 commit（适合后台流水线，避免 rollback 带走日志）
    """
    text = (description or "")[:_MAX_DESC_LEN]
    record = OperationLog(
        user_id=user_id,
        event_type=event_type,
        description=text or None,
    )
    try:
        if db is not None:
            db.add(record)
            await db.flush()
            return

        async with AsyncSessionLocal() as session:
            session.add(record)
            await session.commit()
    except Exception:
        logger.exception("写入操作日志失败: event_type=%s", event_type)
