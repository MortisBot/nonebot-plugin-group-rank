"""group-rank 配置（纯标准库，便于离线测试）。

所有配置项都来自 ``GROUP_RANK_*`` 环境变量，非法值回退默认值。
默认关闭（``GROUP_RANK_ENABLED=0``），且两个榜单的群白名单都为空：不配置就
不会响应任何群，也不会创建数据库。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_TOP_N = 10
DEFAULT_WINDOW_SECONDS = 86400
DEFAULT_BACKFILL_COUNT = 1000
MAX_BACKFILL_COUNT = 1000
DEFAULT_DB_PATH = "data/group_rank/group_rank.db"
DEFAULT_AVATAR_CACHE_DIR = "data/group_rank/avatars"
DEFAULT_AVATAR_TTL_DAYS = 7.0
DEFAULT_AVATAR_MAX_FILES = 500
DEFAULT_COOLDOWN_SECONDS = 10.0
DEFAULT_MEMBER_CACHE_TTL = 600.0
DEFAULT_GROUP_CACHE_TTL = 3600.0
MIN_WINDOW_SECONDS = 3600
MAX_WINDOW_SECONDS = 7 * 86400

_TRUE_VALUES = {"1", "true", "yes", "y", "on", "enable", "enabled"}
_FALSE_VALUES = {"0", "false", "no", "n", "off", "disable", "disabled"}


def _env(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip()


def parse_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return default
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    return default


def parse_int(value: object, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def parse_float(value: object, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def parse_id_set(value: object) -> frozenset[int]:
    """解析逗号/分号/空白分隔的群号集合；非法项忽略。"""
    ids: set[int] = set()
    text = str(value or "")
    for token in (
        text.replace("，", " ")
        .replace("；", " ")
        .replace(",", " ")
        .replace(";", " ")
        .split()
    ):
        number = parse_int(token, 0)
        if number > 0:
            ids.add(number)
    return frozenset(ids)


@dataclass(frozen=True, slots=True)
class GroupRankConfig:
    """插件运行配置（不可变，测试可直接构造）。"""

    enabled: bool
    essence_groups: frozenset[int]
    speak_groups: frozenset[int]
    top_n: int
    window_seconds: int
    backfill_count: int
    db_path: str
    avatar_cache_dir: str
    avatar_ttl_days: float
    avatar_max_files: int
    cooldown_seconds: float
    background: str
    font_dir: str


def load_config() -> GroupRankConfig:
    """从环境变量读取配置；每次调用都重新读取，便于测试与热更新。"""
    window = parse_int(
        _env("GROUP_RANK_WINDOW_SECONDS", str(DEFAULT_WINDOW_SECONDS)),
        DEFAULT_WINDOW_SECONDS,
    )
    backfill = parse_int(
        _env("GROUP_RANK_BACKFILL_COUNT", str(DEFAULT_BACKFILL_COUNT)),
        DEFAULT_BACKFILL_COUNT,
    )
    avatar_ttl_raw = _env(
        "GROUP_RANK_AVATAR_TTL_DAYS",
        _env("GROUP_RANK_AVATAR_TTL", str(DEFAULT_AVATAR_TTL_DAYS)),
    )
    return GroupRankConfig(
        enabled=parse_bool(_env("GROUP_RANK_ENABLED"), False),
        essence_groups=parse_id_set(_env("GROUP_RANK_ESSENCE_GROUPS", "")),
        speak_groups=parse_id_set(_env("GROUP_RANK_SPEAK_GROUPS", "")),
        top_n=min(50, max(1, parse_int(_env("GROUP_RANK_TOP_N"), DEFAULT_TOP_N))),
        window_seconds=max(
            MIN_WINDOW_SECONDS, min(MAX_WINDOW_SECONDS, window)
        ),
        backfill_count=max(0, min(MAX_BACKFILL_COUNT, backfill)),
        db_path=_env("GROUP_RANK_DB_PATH", DEFAULT_DB_PATH) or DEFAULT_DB_PATH,
        avatar_cache_dir=_env(
            "GROUP_RANK_AVATAR_CACHE_DIR", DEFAULT_AVATAR_CACHE_DIR
        )
        or DEFAULT_AVATAR_CACHE_DIR,
        avatar_ttl_days=max(0.0, parse_float(avatar_ttl_raw, DEFAULT_AVATAR_TTL_DAYS)),
        avatar_max_files=max(
            1,
            parse_int(
                _env("GROUP_RANK_AVATAR_MAX_FILES"), DEFAULT_AVATAR_MAX_FILES
            ),
        ),
        cooldown_seconds=max(
            0.0,
            parse_float(
                _env("GROUP_RANK_COOLDOWN_SECONDS"), DEFAULT_COOLDOWN_SECONDS
            ),
        ),
        background=_env("GROUP_RANK_BACKGROUND", ""),
        font_dir=_env("GROUP_RANK_FONT_DIR", ""),
    )


__all__ = [
    "DEFAULT_AVATAR_CACHE_DIR",
    "DEFAULT_BACKFILL_COUNT",
    "DEFAULT_DB_PATH",
    "DEFAULT_TOP_N",
    "GroupRankConfig",
    "MAX_BACKFILL_COUNT",
    "load_config",
    "parse_bool",
    "parse_float",
    "parse_id_set",
    "parse_int",
]
