"""群名 / 群成员信息缓存；成员信息里的 is_robot 即 QQ 官方机器人标记。"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from nonebot import logger
from nonebot.adapters.onebot.v11 import Bot

from .config import GroupRankConfig

_MEMBER_TTL_MAX = 3600.0
_GROUP_TTL = 3600.0
_SEMAPHORE = 8
CALL_TIMEOUT = 12.0


class _TTLCache:
    def __init__(self, max_size: int = 4096) -> None:
        self.max_size = max(16, max_size)
        self.data: dict[tuple[int, int], tuple[float, dict[str, Any]]] = {}

    def get(self, key: tuple[int, int]) -> dict[str, Any] | None:
        hit = self.data.get(key)
        if hit is None:
            return None
        expires, value = hit
        if time.monotonic() >= expires:
            self.data.pop(key, None)
            return None
        return value

    def put(self, key: tuple[int, int], ttl: float, value: dict[str, Any]) -> None:
        self.data[key] = (time.monotonic() + max(0.0, ttl), value)
        while len(self.data) > self.max_size:
            self.data.pop(next(iter(self.data)))

    def clear(self) -> None:
        self.data.clear()


_FULL_LIST_CACHE: dict[int, tuple[float, dict[int, dict[str, Any]]]] = {}
_MEMBER_CACHE = _TTLCache()
_GROUP_NAMES: dict[int, tuple[float, str]] = {}


def _get_group_name_cached(group_id: int) -> str | None:
    hit = _GROUP_NAMES.get(group_id)
    if hit is None:
        return None
    expires, value = hit
    if time.monotonic() >= expires:
        _GROUP_NAMES.pop(group_id, None)
        return None
    return value


async def fetch_group_name(bot: Bot, group_id: int) -> str:
    cached = _get_group_name_cached(group_id)
    if cached is not None:
        return cached
    name = str(group_id)
    try:
        result = await asyncio.wait_for(
            bot.call_api("get_group_info", group_id=int(group_id)),
            timeout=CALL_TIMEOUT,
        )
        if isinstance(result, dict):
            value = str(result.get("group_name") or "").strip()
            if value:
                name = value
    except Exception as exc:  # noqa: BLE001 - 群名只是装饰
        logger.debug(
            "[group_rank] get_group_info failed group={}: {}: {}",
            group_id,
            type(exc).__name__,
            exc,
        )
    _GROUP_NAMES[group_id] = (time.monotonic() + _GROUP_TTL, name)
    return name


async def fetch_group_member_list(
    bot: Bot, group_id: int, cfg: GroupRankConfig
) -> dict[int, dict[str, Any]]:
    """一次拉全量群成员（精华榜用）；失败返回空 dict。"""
    hit = _FULL_LIST_CACHE.get(int(group_id))
    if hit is not None:
        expires, value = hit
        if time.monotonic() < expires:
            return value
        _FULL_LIST_CACHE.pop(int(group_id), None)
    try:
        result = await asyncio.wait_for(
            bot.call_api(
                "get_group_member_list", group_id=int(group_id), no_cache=False
            ),
            timeout=CALL_TIMEOUT,
        )
    except Exception as exc:  # noqa: BLE001 - 成员信息只是装饰
        logger.warning(
            "[group_rank] get_group_member_list failed group={}: {}: {}",
            group_id,
            type(exc).__name__,
            exc,
        )
        return {}
    members: dict[int, dict[str, Any]] = {}
    if isinstance(result, list):
        for item in result:
            if not isinstance(item, dict):
                continue
            try:
                user_id = int(item.get("user_id") or 0)
            except (TypeError, ValueError):
                continue
            if user_id > 0:
                members[user_id] = item
    ttl = max(0.0, min(float(cfg.member_cache_ttl), _MEMBER_TTL_MAX))
    _FULL_LIST_CACHE[int(group_id)] = (time.monotonic() + ttl, members)
    return members


async def _fetch_one(
    bot: Bot, group_id: int, user_id: int, ttl: float
) -> dict[str, Any]:
    key = (int(group_id), int(user_id))
    cached = _MEMBER_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        result = await asyncio.wait_for(
            bot.call_api(
                "get_group_member_info",
                group_id=int(group_id),
                user_id=int(user_id),
                no_cache=False,
            ),
            timeout=CALL_TIMEOUT,
        )
        info = result if isinstance(result, dict) else {}
    except Exception as exc:  # noqa: BLE001 - 成员信息只是装饰
        logger.debug(
            "[group_rank] get_group_member_info failed group={} user={}: {}: {}",
            group_id,
            user_id,
            type(exc).__name__,
            exc,
        )
        return {}
    _MEMBER_CACHE.put(key, min(ttl, _MEMBER_TTL_MAX), info)
    return info


async def fetch_member_infos(
    bot: Bot, group_id: int, user_ids: list[int], cfg: GroupRankConfig
) -> dict[int, dict[str, Any]]:
    """发言榜按需拉成员信息（顺带拿到 is_robot）。"""
    unique = list(dict.fromkeys(int(uid) for uid in user_ids if int(uid) > 0))
    semaphore = asyncio.Semaphore(_SEMAPHORE)

    async def worker(user_id: int) -> tuple[int, dict[str, Any]]:
        async with semaphore:
            return user_id, await _fetch_one(
                bot, group_id, user_id, cfg.member_cache_ttl
            )

    pairs = await asyncio.gather(*(worker(uid) for uid in unique))
    return {user_id: info for user_id, info in pairs}


def clear_caches() -> None:
    _FULL_LIST_CACHE.clear()
    _MEMBER_CACHE.clear()
    _GROUP_NAMES.clear()


__all__ = [
    "clear_caches",
    "fetch_group_member_list",
    "fetch_group_name",
    "fetch_member_infos",
]
