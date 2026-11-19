"""两榜纯逻辑：精华计数、发言过滤、窗口文案。"""

from __future__ import annotations

import time

from nonebot_plugin_group_rank import ranking
from nonebot_plugin_group_rank.model import KIND_ESSENCE, KIND_SPEAK


def test_essence_all_history():
    now = time.time()
    items = [
        {"sender_id": 10001, "sender_nick": "甲", "operator_time": now - 100},
        {"sender_id": 10001, "sender_nick": "甲", "operator_time": now - 200},
        {"sender_id": 10002, "sender_nick": "乙", "operator_time": now - 50},
        {"sender_id": 10003, "sender_nick": "丙", "operator_time": now - 10 * 86400},
        {"sender_id": 10000, "sender_nick": "bot", "operator_time": now - 10},
    ]
    members = {
        10001: {"card": "群昵称甲", "nickname": "QQ甲"},
        10002: {"card": "A君子（脸盲认不出群友）", "nickname": "QQ乙"},
        10003: {"card": "", "nickname": "QQ丙"},
    }
    meta = ranking.build_essence_meta(
        items,
        members,
        group_id=10000,
        group_name="测试群",
        now=now,
        days=None,
        top_n=10,
    )
    assert meta.kind == KIND_ESSENCE
    assert meta.total == 5
    assert meta.group_name == "测试群"
    assert meta.mode_label == "全部历史"
    assert meta.title == "群精华榜"
    top = meta.entries[0]
    assert (top.user_id, top.count, top.name) == (10001, 2, "群昵称甲")
    # 精华是人工操作，bot 不做排除
    assert any(entry.user_id == 10000 for entry in meta.entries)


def test_essence_window_filters_old_and_future():
    now = time.time()
    items = [
        {"sender_id": 10001, "sender_nick": "甲", "operator_time": now - 100},
        {"sender_id": 10001, "sender_nick": "甲", "operator_time": now - 200},
        {"sender_id": 10002, "sender_nick": "乙", "operator_time": now - 50},
        {"sender_id": 10003, "sender_nick": "丙", "operator_time": now - 10 * 86400},
        {"sender_id": 10004, "sender_nick": "丁", "operator_time": now + 3600},
        {"sender_id": 10005, "sender_nick": "戊"},
    ]
    meta = ranking.build_essence_meta(
        items,
        {},
        group_id=10000,
        group_name="测试群",
        now=now,
        days=7,
        top_n=10,
    )
    assert meta.total == 3
    assert [entry.user_id for entry in meta.entries] == [10001, 10002]
    assert meta.mode_label == "近 7 天"
    assert meta.total_label == "当前在库 3 条"


def test_essence_top_n_and_tie_break():
    now = time.time()
    items = [
        {"sender_id": uid, "sender_nick": str(uid), "operator_time": now - 10}
        for uid in (10003, 10001, 10002)
    ]
    meta = ranking.build_essence_meta(
        items, {}, group_id=10000, group_name="g", now=now, days=None, top_n=2
    )
    assert [entry.user_id for entry in meta.entries] == [10001, 10002]
    assert meta.total == 3


def test_essence_name_fallbacks():
    now = time.time()
    items = [{"sender_id": 10001, "sender_nick": "昵称甲", "operator_time": now}]
    # 成员表为空 -> 用精华数据里的昵称
    meta = ranking.build_essence_meta(
        items, {}, group_id=10000, group_name="g", now=now, days=None, top_n=10
    )
    assert meta.entries[0].name == "昵称甲"

    # 群名片字体不支持 -> 回退昵称
    unsafe = "有∫(2778a₀, ∞)4πr²"
    meta = ranking.build_essence_meta(
        items,
        {10001: {"card": unsafe, "nickname": "『落日后的晴天』"}},
        group_id=10000,
        group_name="g",
        now=now,
        days=None,
        top_n=10,
    )
    assert meta.entries[0].name == "『落日后的晴天』"


def test_essence_group_name_fallback():
    now = time.time()
    meta = ranking.build_essence_meta(
        [], {}, group_id=10000, group_name="  ", now=now, days=None, top_n=10
    )
    assert meta.entries == ()
    assert meta.group_name == "10000"


def test_speak_filters_self_and_robots():
    counts = [(10001, 5), (10002, 4), (10003, 3), (10004, 1)]
    infos = {
        10001: {"card": "甲", "nickname": "甲QQ"},
        10002: {"card": "乙", "nickname": "乙QQ", "is_robot": True},
        10003: {"card": "", "nickname": "丙QQ"},
        10004: {"card": "丁", "nickname": "丁QQ"},
    }
    entries, total = ranking.select_speak_entries(
        counts, infos, self_id=10001, top_n=10
    )
    assert [entry.user_id for entry in entries] == [10003, 10004]
    assert total == 4
    assert entries[0].name == "丙QQ"
    assert entries[1].name == "丁"


def test_speak_top_n_keeps_total():
    counts = [(uid, 10 - index) for index, uid in enumerate(range(10001, 10006))]
    entries, total = ranking.select_speak_entries(
        counts, {}, self_id=99999, top_n=3
    )
    assert len(entries) == 3
    assert total == 40


def test_speak_empty():
    entries, total = ranking.select_speak_entries(
        [], {}, self_id=10000, top_n=10
    )
    assert entries == ()
    assert total == 0


def test_build_speak_meta():
    entries = (ranking.RankEntry(user_id=10001, name="甲", count=3),)
    meta = ranking.build_speak_meta(
        entries,
        total=3,
        window_seconds=86400,
        group_id=10000,
        group_name="测试群",
    )
    assert meta.kind == KIND_SPEAK
    assert meta.title == "群发言榜"
    assert meta.total_label == "发言 3 条"
    assert meta.mode_label == "近 24 小时"


def test_window_label():
    assert ranking.window_label(86400) == "近 24 小时"
    assert ranking.window_label(604800) == "近 7 天"
    assert ranking.window_label(7200) == "近 2 小时"
    assert ranking.window_label(90) == "近 90 秒"
