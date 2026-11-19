"""配置默认值 / 解析 / 边界钳制。"""

from __future__ import annotations

import dataclasses

import pytest
from nonebot_plugin_group_rank.config import (
    DEFAULT_BACKFILL_COUNT,
    DEFAULT_DB_PATH,
    DEFAULT_TOP_N,
    load_config,
    parse_bool,
    parse_float,
    parse_id_set,
    parse_int,
)


def test_defaults_are_safe():
    cfg = load_config()
    assert cfg.enabled is False
    assert cfg.essence_groups == frozenset()
    assert cfg.speak_groups == frozenset()
    assert cfg.top_n == DEFAULT_TOP_N == 10
    assert cfg.window_seconds == 86400
    assert cfg.backfill_count == DEFAULT_BACKFILL_COUNT == 1000
    assert cfg.db_path == DEFAULT_DB_PATH == "data/group_rank/group_rank.db"
    assert cfg.avatar_cache_dir == "data/group_rank/avatars"
    assert cfg.avatar_ttl_days == 7.0
    assert cfg.avatar_max_files == 500
    assert cfg.cooldown_seconds == 10.0
    assert cfg.background == ""
    assert cfg.font_dir == ""


def test_env_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("GROUP_RANK_ENABLED", "1")
    monkeypatch.setenv("GROUP_RANK_ESSENCE_GROUPS", "10000, 10001")
    monkeypatch.setenv("GROUP_RANK_SPEAK_GROUPS", "10000；10002 10003")
    monkeypatch.setenv("GROUP_RANK_TOP_N", "15")
    monkeypatch.setenv("GROUP_RANK_WINDOW_SECONDS", "7200")
    monkeypatch.setenv("GROUP_RANK_BACKFILL_COUNT", "200")
    monkeypatch.setenv("GROUP_RANK_DB_PATH", str(tmp_path / "rank.db"))
    monkeypatch.setenv("GROUP_RANK_AVATAR_CACHE_DIR", str(tmp_path / "av"))
    monkeypatch.setenv("GROUP_RANK_AVATAR_TTL_DAYS", "1.5")
    monkeypatch.setenv("GROUP_RANK_AVATAR_MAX_FILES", "42")
    monkeypatch.setenv("GROUP_RANK_COOLDOWN_SECONDS", "0")
    monkeypatch.setenv("GROUP_RANK_BACKGROUND", str(tmp_path / "bg.png"))
    monkeypatch.setenv("GROUP_RANK_FONT_DIR", str(tmp_path / "fonts"))

    cfg = load_config()
    assert cfg.enabled is True
    assert cfg.essence_groups == frozenset({10000, 10001})
    assert cfg.speak_groups == frozenset({10000, 10002, 10003})
    assert cfg.top_n == 15
    assert cfg.window_seconds == 7200
    assert cfg.backfill_count == 200
    assert cfg.db_path == str(tmp_path / "rank.db")
    assert cfg.avatar_cache_dir == str(tmp_path / "av")
    assert cfg.avatar_ttl_days == 1.5
    assert cfg.avatar_max_files == 42
    assert cfg.cooldown_seconds == 0.0
    assert cfg.background == str(tmp_path / "bg.png")
    assert cfg.font_dir == str(tmp_path / "fonts")


def test_clamps(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GROUP_RANK_TOP_N", "999")
    monkeypatch.setenv("GROUP_RANK_WINDOW_SECONDS", "1")
    monkeypatch.setenv("GROUP_RANK_BACKFILL_COUNT", "99999")
    cfg = load_config()
    assert cfg.top_n == 50
    assert cfg.window_seconds == 3600
    assert cfg.backfill_count == 1000

    monkeypatch.setenv("GROUP_RANK_TOP_N", "0")
    monkeypatch.setenv("GROUP_RANK_WINDOW_SECONDS", "999999999")
    monkeypatch.setenv("GROUP_RANK_BACKFILL_COUNT", "-5")
    cfg = load_config()
    assert cfg.top_n == 1
    assert cfg.window_seconds == 7 * 86400
    assert cfg.backfill_count == 0

    monkeypatch.setenv("GROUP_RANK_TOP_N", "abc")
    monkeypatch.setenv("GROUP_RANK_WINDOW_SECONDS", "abc")
    monkeypatch.setenv("GROUP_RANK_BACKFILL_COUNT", "abc")
    cfg = load_config()
    assert (cfg.top_n, cfg.window_seconds, cfg.backfill_count) == (10, 86400, 1000)


def test_invalid_values_fall_back(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GROUP_RANK_ENABLED", "maybe")
    monkeypatch.setenv("GROUP_RANK_AVATAR_TTL_DAYS", "oops")
    cfg = load_config()
    assert cfg.enabled is False
    assert cfg.avatar_ttl_days == 7.0


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", True),
        ("true", True),
        ("on", True),
        ("0", False),
        ("false", False),
        ("off", False),
        ("", False),
        (None, False),
        ("whatever", False),
        (True, True),
    ],
)
def test_parse_bool(value, expected):
    assert parse_bool(value, default=False) is expected


def test_parse_numbers():
    assert parse_int("12") == 12
    assert parse_int("12.7") == 0
    assert parse_int(None, 5) == 5
    assert parse_float("1.25") == 1.25
    assert parse_float("x", 3.5) == 3.5


def test_parse_id_set():
    assert parse_id_set("10000,10001") == frozenset({10000, 10001})
    assert parse_id_set("10000；10001 10002") == frozenset({10000, 10001, 10002})
    assert parse_id_set("0 -1 abc 10000") == frozenset({10000})
    assert parse_id_set("") == frozenset()


def test_config_is_frozen(cfg):
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.top_n = 3  # type: ignore[misc]


def test_font_and_background_unset_by_default():
    cfg = load_config()
    assert cfg.background == ""
    assert cfg.font_dir == ""
