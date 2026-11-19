"""两种榜单的纯逻辑：精华计数与发言 Top N（纯标准库）。"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from .model import (
    KIND_ESSENCE,
    KIND_SPEAK,
    RankEntry,
    RankImageMeta,
    safe_display_name,
    safe_group_name,
)


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _text(value: object) -> str:
    return str(value or "").strip()


def build_essence_meta(
    items: list[dict[str, Any]],
    members: Mapping[int, Mapping[str, Any]],
    *,
    group_id: int,
    group_name: object,
    now: float,
    days: int | None,
    top_n: int,
) -> RankImageMeta:
    """按精华消息的发送者计数；``days=None`` 表示全部历史。

    与源插件一致：精华数据里的 ``operator_time`` 是「被设为精华」的时间，
    窗口过滤按它算；QQ 官方机器人不做排除（精华是人工操作的结果）。
    """
    cutoff: float | None = None
    if days is not None:
        cutoff = float(now) - int(days) * 86400.0

    counts: Counter[int] = Counter()
    sender_nicks: dict[int, str] = {}
    for item in items:
        if not isinstance(item, Mapping):
            continue
        sender_id = _to_int(item.get("sender_id"), 0)
        if sender_id <= 0:
            continue
        if cutoff is not None:
            operator_time = _to_int(item.get("operator_time"), 0)
            if operator_time <= 0 or operator_time < cutoff or operator_time > now:
                continue
        counts[sender_id] += 1
        if sender_id not in sender_nicks:
            sender_nicks[sender_id] = _text(item.get("sender_nick"))

    total = sum(counts.values())
    top = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[
        : max(1, int(top_n))
    ]

    entries: list[RankEntry] = []
    for sender_id, count in top:
        member = members.get(sender_id) or {}
        card = _text(member.get("card")) if isinstance(member, Mapping) else ""
        nickname = (
            _text(member.get("nickname")) if isinstance(member, Mapping) else ""
        )
        name = safe_display_name(card, nickname, sender_id)
        if name == str(sender_id) and sender_nicks.get(sender_id):
            fallback = safe_display_name("", sender_nicks[sender_id], sender_id)
            if fallback and fallback != str(sender_id):
                name = fallback
        entries.append(RankEntry(user_id=sender_id, name=name, count=count))

    mode_label = "全部历史" if days is None else f"近 {days} 天"
    return RankImageMeta(
        kind=KIND_ESSENCE,
        group_name=safe_group_name(group_name, group_id),
        mode_label=mode_label,
        total=total,
        entries=tuple(entries),
    )


def select_speak_entries(
    counts: list[tuple[int, int]],
    infos: Mapping[int, Mapping[str, Any]],
    *,
    self_id: int,
    top_n: int,
) -> tuple[tuple[RankEntry, ...], int]:
    """过滤 bot 自己与 QQ 官方机器人，生成 Top N；返回 (entries, 参与总数)。"""
    entries: list[RankEntry] = []
    total = 0
    for user_id, count in counts:
        if user_id == self_id:
            continue
        info = infos.get(user_id) or {}
        if bool(info.get("is_robot")):
            continue
        total += int(count)
        if len(entries) >= top_n:
            continue
        name = safe_display_name(info.get("card"), info.get("nickname"), user_id)
        entries.append(RankEntry(user_id=user_id, name=name, count=int(count)))
    return tuple(entries), total


def build_speak_meta(
    entries: tuple[RankEntry, ...],
    *,
    total: int,
    window_seconds: int,
    group_id: int,
    group_name: object,
) -> RankImageMeta:
    return RankImageMeta(
        kind=KIND_SPEAK,
        group_name=safe_group_name(group_name, group_id),
        mode_label=window_label(window_seconds),
        total=total,
        entries=entries,
    )


def window_label(window_seconds: int) -> str:
    seconds = max(1, int(window_seconds))
    if seconds <= 86400 and seconds % 3600 == 0:
        return f"近 {seconds // 3600} 小时"
    if seconds % 86400 == 0:
        return f"近 {seconds // 86400} 天"
    if seconds % 3600 == 0:
        return f"近 {seconds // 3600} 小时"
    return f"近 {seconds} 秒"


__all__ = [
    "build_essence_meta",
    "build_speak_meta",
    "select_speak_entries",
    "window_label",
]
