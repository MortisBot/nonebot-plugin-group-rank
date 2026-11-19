"""发言榜历史回填：``get_group_msg_history`` 拉最近消息，写库后按窗口过滤。

回填只在新群第一次出榜时做一次（marker 存在 meta 表）；单群上限
``GROUP_RANK_BACKFILL_COUNT``，硬上限 1000 条，避免一次拉爆 NapCat。
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping

from nonebot import logger
from nonebot.adapters.onebot.v11 import Bot

from .config import MAX_BACKFILL_COUNT, GroupRankConfig
from .store import add_messages

CALL_TIMEOUT = 20.0


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def normalize_history_messages(
    data: object,
    *,
    group_id: int,
    now: float,
    window_seconds: int,
) -> list[tuple[int, int, str, int]]:
    """把 NapCat 历史消息归一成 ``(group_id, user_id, message_id, ts)``。

    兼容 ``{"messages": [...]}`` 与裸列表两种返回；无 message_id 的消息用
    合成 id，时间戳超出窗口的直接丢弃。
    """
    if isinstance(data, Mapping):
        messages = data.get("messages")
    else:
        messages = data
    if not isinstance(messages, list):
        return []

    cutoff = int(now) - int(window_seconds)
    rows: list[tuple[int, int, str, int]] = []
    for index, item in enumerate(messages):
        if not isinstance(item, Mapping):
            continue
        user_id = _to_int(item.get("user_id"), 0)
        ts = _to_int(item.get("time"), 0)
        if user_id <= 0 or ts <= 0:
            continue
        if ts < cutoff or ts > now + 300:
            continue
        message_id = item.get("message_id")
        if message_id is None:
            message_id = item.get("real_id")
        if message_id is None:
            message_id = item.get("message_seq")
        if message_id is None:
            message_id = f"h:{group_id}:{user_id}:{ts}:{index}"
        rows.append((int(group_id), user_id, str(message_id), ts))
    return rows


def backfill_count(cfg: GroupRankConfig) -> int:
    return max(0, min(int(cfg.backfill_count), MAX_BACKFILL_COUNT))


async def backfill_group(bot: Bot, group_id: int, cfg: GroupRankConfig) -> int:
    """拉取最近消息并入库，返回写入行数。"""
    count = backfill_count(cfg)
    if count <= 0:
        return 0
    result = await asyncio.wait_for(
        bot.call_api(
            "get_group_msg_history",
            group_id=int(group_id),
            count=count,
        ),
        timeout=CALL_TIMEOUT,
    )
    rows = normalize_history_messages(
        result,
        group_id=group_id,
        now=time.time(),
        window_seconds=cfg.window_seconds,
    )
    if rows:
        await asyncio.to_thread(add_messages, cfg.db_path, rows)
    logger.info(
        "[group_rank] backfill group={} requested={} rows={}",
        group_id,
        count,
        len(rows),
    )
    return len(rows)


__all__ = ["backfill_count", "backfill_group", "normalize_history_messages"]
