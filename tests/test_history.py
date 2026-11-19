"""发言榜历史回填：归一化、窗口过滤、1000 条上限、假 Bot 调用。"""

from __future__ import annotations

import dataclasses
import time

from nonebot_plugin_group_rank import history, store


def test_normalize_dict_payload():
    now = 1_900_000_000.0
    payload = {
        "messages": [
            {"user_id": 10001, "time": int(now) - 10, "message_id": 1},
            {"user_id": 10002, "time": int(now) - 20, "real_id": 2},
            {"user_id": 10003, "time": int(now) - 30, "message_seq": 3},
            {"user_id": 10004, "time": int(now) - 40},
        ]
    }
    rows = history.normalize_history_messages(
        payload, group_id=10000, now=now, window_seconds=86400
    )
    assert rows[:3] == [
        (10000, 10001, "1", int(now) - 10),
        (10000, 10002, "2", int(now) - 20),
        (10000, 10003, "3", int(now) - 30),
    ]
    # 没有消息 id 时合成，保证回填可去重
    assert rows[3][0] == 10000 and rows[3][1] == 10004
    assert rows[3][2].startswith("h:10000:10004:")


def test_normalize_list_payload_and_window():
    now = 1_900_000_000.0
    rows = history.normalize_history_messages(
        [
            {"user_id": 10001, "time": int(now) - 10, "message_id": 1},
            {"user_id": 10001, "time": int(now) - 3 * 86400, "message_id": 2},
            {"user_id": 10001, "time": int(now) + 600, "message_id": 3},
            {"user_id": 10001, "time": int(now) + 30, "message_id": 4},
            {"user_id": 0, "time": int(now) - 10, "message_id": 5},
            {"user_id": 10002, "time": 0, "message_id": 6},
            "not-a-mapping",
        ],
        group_id=10000,
        now=now,
        window_seconds=86400,
    )
    assert [row[2] for row in rows] == ["1", "4"]


def test_normalize_handles_garbage():
    assert history.normalize_history_messages(
        None, group_id=10000, now=time.time(), window_seconds=86400
    ) == []
    assert history.normalize_history_messages(
        {"messages": "nope"}, group_id=10000, now=time.time(), window_seconds=86400
    ) == []


def test_backfill_count_clamped(cfg):
    assert history.backfill_count(dataclasses.replace(cfg, backfill_count=50000)) == 1000
    assert history.backfill_count(dataclasses.replace(cfg, backfill_count=0)) == 0
    assert history.backfill_count(cfg) == 1000


async def test_backfill_group_writes_rows(cfg, fake_bot):
    now = int(time.time())
    bot = fake_bot(
        {
            "get_group_msg_history": {
                "messages": [
                    {"user_id": 10001, "time": now - 10, "message_id": 11},
                    {"user_id": 10002, "time": now - 20, "message_id": 12},
                ]
            }
        }
    )
    store.init_db(cfg.db_path)
    rows = await history.backfill_group(bot, 10000, cfg)
    assert rows == 2
    assert bot.calls[0][0] == "get_group_msg_history"
    assert bot.calls[0][1]["group_id"] == 10000
    assert bot.calls[0][1]["count"] == 1000
    assert store.counts_since(cfg.db_path, 10000, now - 3600) == [
        (10001, 1),
        (10002, 1),
    ]


async def test_backfill_group_disabled(fake_bot, cfg):
    bot = fake_bot({})
    rows = await history.backfill_group(
        bot, 10000, dataclasses.replace(cfg, backfill_count=0)
    )
    assert rows == 0
    assert bot.calls == []


async def test_backfill_group_propagates_api_error(cfg, fake_bot):
    bot = fake_bot({"get_group_msg_history": RuntimeError("napcat down")})
    store.init_db(cfg.db_path)
    try:
        await history.backfill_group(bot, 10000, cfg)
    except RuntimeError as exc:
        assert "napcat down" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("API 异常应向上抛，交给插件记录并延后重试")
