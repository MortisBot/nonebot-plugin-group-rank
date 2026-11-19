"""发言榜 SQLite 存储：只存 group_id / user_id / message_id / ts。

不存消息内容；由标准库 sqlite3 实现，方便离线自检。
"""

from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Iterable
from pathlib import Path

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    message_id TEXT NOT NULL,
    ts INTEGER NOT NULL,
    PRIMARY KEY (group_id, message_id)
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""

_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_group_rank_messages_group_ts "
    "ON messages(group_id, ts)"
)


def _connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10.0)
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db(db_path: str | Path) -> None:
    conn = _connect(db_path)
    try:
        conn.executescript(_SCHEMA)
        conn.execute(_INDEX)
        conn.commit()
    finally:
        conn.close()


def try_init_db(db_path: str | Path) -> bool:
    """初始化数据库；失败只记日志，返回 False（插件不因此崩溃）。"""
    try:
        init_db(db_path)
        return True
    except Exception:  # noqa: BLE001 - 数据库不可用时插件降级
        logger.warning(
            "[group_rank] 初始化数据库失败 path=%s", db_path, exc_info=True
        )
        return False


def add_message(
    db_path: str | Path,
    group_id: int,
    user_id: int,
    message_id: object,
    ts: int,
) -> bool:
    """写入一条消息记录；``(group_id, message_id)`` 重复时返回 False。"""
    conn = _connect(db_path)
    try:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO messages(group_id, user_id, message_id, ts) "
            "VALUES(?, ?, ?, ?)",
            (int(group_id), int(user_id), str(message_id), int(ts)),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def add_messages(
    db_path: str | Path,
    rows: Iterable[tuple[int, int, object, int]],
) -> int:
    conn = _connect(db_path)
    try:
        cursor = conn.executemany(
            "INSERT OR IGNORE INTO messages(group_id, user_id, message_id, ts) "
            "VALUES(?, ?, ?, ?)",
            [
                (int(group_id), int(user_id), str(message_id), int(ts))
                for group_id, user_id, message_id, ts in rows
            ],
        )
        conn.commit()
        return max(0, int(cursor.rowcount))
    finally:
        conn.close()


def counts_since(
    db_path: str | Path, group_id: int, since_ts: int
) -> list[tuple[int, int]]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT user_id, COUNT(*) AS n FROM messages "
            "WHERE group_id = ? AND ts >= ? "
            "GROUP BY user_id ORDER BY n DESC, user_id ASC",
            (int(group_id), int(since_ts)),
        ).fetchall()
        return [(int(row[0]), int(row[1])) for row in rows]
    finally:
        conn.close()


def prune_before(db_path: str | Path, before_ts: int) -> int:
    conn = _connect(db_path)
    try:
        cursor = conn.execute(
            "DELETE FROM messages WHERE ts < ?", (int(before_ts),)
        )
        conn.commit()
        return max(0, int(cursor.rowcount))
    finally:
        conn.close()


def mark_backfilled(
    db_path: str | Path, group_id: int, at: int | None = None
) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
            (f"backfill:{int(group_id)}", str(int(at or time.time()))),
        )
        conn.commit()
    finally:
        conn.close()


def is_backfilled(db_path: str | Path, group_id: int) -> bool:
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = ?",
            (f"backfill:{int(group_id)}",),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


__all__ = [
    "add_message",
    "add_messages",
    "counts_since",
    "init_db",
    "is_backfilled",
    "mark_backfilled",
    "prune_before",
    "try_init_db",
]
