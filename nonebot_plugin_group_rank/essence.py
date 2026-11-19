"""精华榜数据获取：NapCat ``get_essence_msg_list`` 实时拉取，不落库。"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from nonebot import logger
from nonebot.adapters.onebot.v11 import Bot

from .config import GroupRankConfig
from .members import fetch_group_member_list, fetch_group_name
from .model import RankDataError, RankImageMeta
from .ranking import build_essence_meta

CALL_TIMEOUT = 15.0


async def fetch_essence_list(bot: Bot, group_id: int) -> list[dict[str, Any]]:
    """拉当前在库的精华消息；接口异常/格式不对抛 RankDataError。"""
    try:
        result = await asyncio.wait_for(
            bot.call_api("get_essence_msg_list", group_id=str(int(group_id))),
            timeout=CALL_TIMEOUT,
        )
    except Exception as exc:  # noqa: BLE001 - 统一转成 RankDataError
        raise RankDataError(
            f"get_essence_msg_list failed: {type(exc).__name__}"
        ) from exc
    if not isinstance(result, list):
        raise RankDataError("get_essence_msg_list returned non-list")
    return [item for item in result if isinstance(item, dict)]


async def collect_essence_meta(
    bot: Bot, group_id: int, days: int | None, cfg: GroupRankConfig
) -> RankImageMeta:
    """拉取精华 + 成员 + 群名，生成渲染数据。"""
    items = await fetch_essence_list(bot, group_id)
    members_result, group_result = await asyncio.gather(
        fetch_group_member_list(bot, group_id, cfg),
        fetch_group_name(bot, group_id),
        return_exceptions=True,
    )
    if isinstance(members_result, BaseException):
        logger.warning(
            "[group_rank] 获取群成员失败 group={} err={}",
            group_id,
            type(members_result).__name__,
        )
        members: dict[int, dict[str, Any]] = {}
    else:
        members = members_result
    group_name: object = (
        str(group_id)
        if isinstance(group_result, BaseException)
        else group_result
    )

    return build_essence_meta(
        items,
        members,
        group_id=int(group_id),
        group_name=group_name,
        now=time.time(),
        days=days,
        top_n=cfg.top_n,
    )


__all__ = ["collect_essence_meta", "fetch_essence_list"]
