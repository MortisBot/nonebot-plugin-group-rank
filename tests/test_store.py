"""SQLite 存储：计数、去重、窗口、回填 marker、DB 容错。"""

from __future__ import annotations

import time

from nonebot_plugin_group_rank import store


def test_insert_and_dedupe(tmp_path):
    db = tmp_path / "rank.db"
    store.init_db(db)
    assert db.is_file()
    now = int(time.time())
    assert store.add_message(db, 10000, 10001, 1001, now - 10) is True
    # 同 (group_id, message_id) 不重复计数
    assert store.add_message(db, 10000, 10001, 1001, now - 10) is False


def test_counts_since_sorted_and_windowed(tmp_path):
    db = tmp_path / "rank.db"
    store.init_db(db)
    now = int(time.time())
    store.add_messages(
        db,
        [
            (10000, 10001, 2001, now - 20),
            (10000, 10001, 2002, now - 30),
            (10000, 10002, 2003, now - 40),
            (10000, 10002, 2004, now - 50),
            (10000, 10003, 2005, now - 25 * 3600),
            (10001, 10001, 2006, now - 10),
        ],
    )
    counts = store.counts_since(db, 10000, now - 86400)
    assert counts == [(10001, 2), (10002, 2)]
    assert store.counts_since(db, 10000, now - 25) == [(10001, 1)]
    assert store.counts_since(db, 99999, 0) == []


def test_prune_before(tmp_path):
    db = tmp_path / "rank.db"
    store.init_db(db)
    now = int(time.time())
    store.add_messages(
        db,
        [
            (10000, 10001, 3001, now - 10),
            (10000, 10001, 3002, now - 2 * 86400),
            (10000, 10001, 3003, now - 3 * 86400),
        ],
    )
    removed = store.prune_before(db, now - 86400)
    assert removed == 2
    assert store.counts_since(db, 10000, 0) == [(10001, 1)]


def test_backfill_marker(tmp_path):
    db = tmp_path / "rank.db"
    store.init_db(db)
    assert store.is_backfilled(db, 10000) is False
    store.mark_backfilled(db, 10000)
    assert store.is_backfilled(db, 10000) is True
    assert store.is_backfilled(db, 10001) is False


def test_init_is_idempotent(tmp_path):
    db = tmp_path / "nested" / "rank.db"
    store.init_db(db)
    store.init_db(db)
    store.add_message(db, 10000, 10001, 1, int(time.time()))
    assert store.counts_since(db, 10000, 0) == [(10001, 1)]


def test_try_init_db_reports_failure(tmp_path):
    # 传一个已存在的目录：sqlite 无法打开，插件层应降级而不是抛错
    assert store.try_init_db(tmp_path) is False


def test_try_init_db_success(tmp_path):
    assert store.try_init_db(tmp_path / "ok.db") is True
