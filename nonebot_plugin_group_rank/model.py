"""榜单数据结构与文本清洗（纯标准库，不依赖 NoneBot / Pillow）。"""

from __future__ import annotations

import re
from dataclasses import dataclass

KIND_ESSENCE = "essence"
KIND_SPEAK = "speak"

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SPACE_RE = re.compile(r"\s+")
_SAFE_EXTRA = set("（）、，。·_-.!?！？~～♡『』「」【】:：;；/／+＋&＆@#＃ ")


class RankDataError(RuntimeError):
    """榜单数据不可用（接口失败/格式异常）。"""


@dataclass(frozen=True, slots=True)
class RankRequest:
    """一条合法命令的解析结果。"""

    kind: str
    days: int | None = None


@dataclass(frozen=True, slots=True)
class RankEntry:
    user_id: int
    name: str
    count: int


@dataclass(frozen=True, slots=True)
class RankImageMeta:
    """渲染所需的全部榜单信息（两种榜单共用）。"""

    kind: str
    group_name: str
    mode_label: str
    total: int
    entries: tuple[RankEntry, ...]

    @property
    def title(self) -> str:
        return "群精华榜" if self.kind == KIND_ESSENCE else "群发言榜"

    @property
    def total_label(self) -> str:
        if self.kind == KIND_ESSENCE:
            return f"当前在库 {self.total} 条"
        return f"发言 {self.total} 条"


def clean_text(value: object) -> str:
    text = _CONTROL_RE.sub("", str(value or ""))
    return _SPACE_RE.sub(" ", text).strip()


def _char_safe(ch: str) -> bool:
    code = ord(ch)
    if 0x4E00 <= code <= 0x9FFF or 0x3400 <= code <= 0x4DBF:
        return True
    if 0x3040 <= code <= 0x30FF:
        return True
    if ch in _SAFE_EXTRA:
        return True
    return ch.isascii() and (ch.isalnum() or ch in _SAFE_EXTRA)


def safe_display_name(card: object, nickname: object, user_id: int) -> str:
    """群名片优先；字体不支持的名字回退昵称，再回退 QQ 号。"""
    card_text = clean_text(card)
    nick_text = clean_text(nickname)
    for raw in (card_text, nick_text):
        if raw and all(_char_safe(ch) for ch in raw):
            return raw
    for raw in (card_text, nick_text):
        cleaned = "".join(ch for ch in raw if _char_safe(ch)).strip()
        if cleaned:
            return cleaned
    return str(user_id)


def safe_group_name(name: object, group_id: int) -> str:
    text = clean_text(name)
    if not text:
        return str(group_id)
    if all(_char_safe(ch) for ch in text):
        return text
    cleaned = "".join(ch for ch in text if _char_safe(ch)).strip()
    return cleaned or str(group_id)


def safe_initial(name: object) -> str:
    text = clean_text(name)
    for ch in text:
        if _char_safe(ch):
            return ch
    return "♪"


__all__ = [
    "KIND_ESSENCE",
    "KIND_SPEAK",
    "RankDataError",
    "RankEntry",
    "RankImageMeta",
    "RankRequest",
    "clean_text",
    "safe_display_name",
    "safe_group_name",
    "safe_initial",
]
