"""命令解析与 @bot 判定（纯标准库，不 import NoneBot）。

支持的命令：
    ``精华榜``      当前在库的全部精华（NapCat 实时数据）
    ``精华榜 N``    近 N×24 小时被设为精华的
    ``发言榜``      ``GROUP_RANK_WINDOW_SECONDS`` 窗口内的发言次数
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .model import KIND_ESSENCE, KIND_SPEAK, RankRequest

_ESSENCE_RE = re.compile(r"^精华榜(?:\s*([1-9][0-9]*))?$")
_SPEAK_RE = re.compile(r"^发言榜$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SPACE_RE = re.compile(r"\s+")


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def iter_segments(message: Any) -> list[Any]:
    if message is None or isinstance(message, str):
        return []
    try:
        return list(message)
    except TypeError:
        return []


def segment_type(segment: Any) -> str:
    return str(_get(segment, "type", "") or "")


def segment_data(segment: Any) -> Mapping[str, Any]:
    data = _get(segment, "data", None)
    return data if isinstance(data, Mapping) else {}


def normalize_text(value: object) -> str:
    text = _CONTROL_RE.sub("", str(value or ""))
    return _SPACE_RE.sub(" ", text).strip()


def has_at_self(event: Any) -> bool:
    """扫描 original_message，确认显式 @ 了 bot（不依赖 to_me）。"""
    self_id = str(_get(event, "self_id", "") or "")
    if not self_id:
        return False
    original = _get(event, "original_message", None)
    if original is None:
        original = _get(event, "message", None)
    for segment in iter_segments(original):
        if segment_type(segment) != "at":
            continue
        if str(segment_data(segment).get("qq", "")) == self_id:
            return True
    return False


def event_plaintext(event: Any) -> str:
    getter = getattr(event, "get_plaintext", None)
    if callable(getter):
        text: Any = None
        try:
            text = getter()
        except Exception:
            text = None
        if isinstance(text, str) and text:
            return text
    parts = []
    for segment in iter_segments(_get(event, "message", None)):
        if segment_type(segment) == "text":
            parts.append(str(segment_data(segment).get("text", "") or ""))
    return "".join(parts)


def parse_rank_command(text: object) -> RankRequest | None:
    """把文本解析成榜单请求；不合法返回 None。"""
    normalized = normalize_text(text)
    match = _ESSENCE_RE.match(normalized)
    if match:
        days_text = match.group(1)
        if days_text is None:
            return RankRequest(kind=KIND_ESSENCE, days=None)
        return RankRequest(kind=KIND_ESSENCE, days=max(1, int(days_text)))
    if _SPEAK_RE.match(normalized):
        return RankRequest(kind=KIND_SPEAK, days=None)
    return None


__all__ = [
    "event_plaintext",
    "has_at_self",
    "iter_segments",
    "normalize_text",
    "parse_rank_command",
    "segment_data",
    "segment_type",
]
