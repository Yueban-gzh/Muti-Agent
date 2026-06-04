"""
SQLite 增量迁移：为已有数据库添加交流期 / 收束期新字段与新表。
create_all 不会 ALTER 已存在表，启动时调用本模块。
"""

import logging
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

logger = logging.getLogger("db.migrate")


def _columns(conn: Connection, table: str) -> set[str]:
    insp = inspect(conn)
    return {c["name"] for c in insp.get_columns(table)}


def _add_column(conn: Connection, table: str, ddl: str) -> None:
    try:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))
        logger.info("迁移: %s ADD %s", table, ddl.split()[0])
    except Exception as e:
        if "duplicate column" in str(e).lower():
            return
        raise


def run_schema_migrations(sync_conn: Connection) -> None:
    """在 sync 连接上执行迁移（由 async engine.run_sync 调用）。"""
    cols = _columns(sync_conn, "decision_tasks")
    if "context_notes" not in cols:
        _add_column(sync_conn, "decision_tasks", "context_notes TEXT")
    if "discussion_turns" not in cols:
        _add_column(sync_conn, "decision_tasks", "discussion_turns INTEGER NOT NULL DEFAULT 0")
    if "debate_exchange_rounds" not in cols:
        _add_column(sync_conn, "decision_tasks", "debate_exchange_rounds INTEGER NOT NULL DEFAULT 0")
    if "discussion_summary" not in cols:
        _add_column(sync_conn, "decision_tasks", "discussion_summary TEXT")
    if "summary_method" not in cols:
        _add_column(sync_conn, "decision_tasks", "summary_method VARCHAR(20)")
    if "finalized_at" not in cols:
        _add_column(sync_conn, "decision_tasks", "finalized_at DATETIME")

    ta = _columns(sync_conn, "task_agents")
    if "stance" not in ta:
        _add_column(sync_conn, "task_agents", "stance VARCHAR(20)")
    if "template_id" not in ta:
        _add_column(sync_conn, "task_agents", "template_id INTEGER")
    if "extra_notes" not in ta:
        _add_column(sync_conn, "task_agents", "extra_notes TEXT")
    if "sort_order" not in ta:
        _add_column(sync_conn, "task_agents", "sort_order INTEGER NOT NULL DEFAULT 0")

    ao = _columns(sync_conn, "agent_outputs")
    if "phase" not in ao:
        _add_column(sync_conn, "agent_outputs", "phase VARCHAR(20) NOT NULL DEFAULT 'final'")
    if "round" not in ao:
        _add_column(sync_conn, "agent_outputs", "round INTEGER NOT NULL DEFAULT 1")

    tpl = _columns(sync_conn, "agent_templates")
    if "default_stance" not in tpl:
        _add_column(sync_conn, "agent_templates", "default_stance VARCHAR(20)")
    if "recommended_modes" not in tpl:
        _add_column(sync_conn, "agent_templates", "recommended_modes TEXT")
    if "sort_order" not in tpl:
        _add_column(sync_conn, "agent_templates", "sort_order INTEGER NOT NULL DEFAULT 0")
    if "display_alias" not in tpl:
        _add_column(sync_conn, "agent_templates", "display_alias VARCHAR(100)")

    insp = inspect(sync_conn)
    if "discussion_messages" not in insp.get_table_names():
        sync_conn.execute(
            text(
                """
                CREATE TABLE discussion_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    seq INTEGER NOT NULL,
                    role VARCHAR(20) NOT NULL,
                    task_agent_id INTEGER,
                    target_agent_id INTEGER,
                    reply_scope VARCHAR(30),
                    content TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES decision_tasks(id) ON DELETE CASCADE,
                    FOREIGN KEY(task_agent_id) REFERENCES task_agents(id) ON DELETE SET NULL,
                    FOREIGN KEY(target_agent_id) REFERENCES task_agents(id) ON DELETE SET NULL
                )
                """
            )
        )
        sync_conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_discussion_messages_task_seq "
                "ON discussion_messages (task_id, seq)"
            )
        )
        logger.info("迁移: 已创建 discussion_messages 表")
