"""插件装配：metadata、@bot/白名单规则、懒初始化、冷却。"""

from __future__ import annotations

import dataclasses
import time
from pathlib import Path

import nonebot_plugin_group_rank as plugin
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageSegment
from nonebot_plugin_group_rank.model import KIND_ESSENCE, KIND_SPEAK
from nonebot_plugin_group_rank.parse import parse_rank_command

GROUP = 10000
SELF = 10000
USER = 10001


def make_event(
    text: str = "精华榜",
    *,
    at: bool = True,
    group_id: int = GROUP,
    user_id: int = USER,
) -> GroupMessageEvent:
    message = Message(
        [MessageSegment.at(SELF), MessageSegment.text(" " + text)]
        if at
        else [MessageSegment.text(text)]
    )
    return GroupMessageEvent.model_validate(
        {
            "time": int(time.time()),
            "self_id": SELF,
            "post_type": "message",
            "sub_type": "normal",
            "user_id": user_id,
            "message_id": 123456,
            "message_type": "group",
            "message": message,
            "original_message": message,
            "raw_message": text,
            "font": 0,
            "sender": {"user_id": user_id, "nickname": "tester"},
            "group_id": group_id,
            "to_me": at,
        }
    )


def test_metadata():
    meta = plugin.__plugin_meta__
    assert meta.name == "group-rank"
    assert meta.supported_adapters == {"~onebot.v11"}
    assert "精华榜" in meta.usage
    assert "发言榜" in meta.usage


def test_matchers_registered():
    assert plugin.essence_matcher is not None
    assert plugin.speak_matcher is not None
    assert plugin.record_matcher is not None
    assert plugin.essence_matcher.priority == 6
    assert plugin.speak_matcher.priority == 6
    assert plugin.record_matcher.priority == 99


def test_candidate_requires_enabled_and_whitelist(monkeypatch, cfg):
    monkeypatch.setattr(plugin, "CFG", cfg)
    event = make_event("精华榜")
    assert plugin._candidate(event, KIND_ESSENCE) is True
    # 发言榜命令走发言榜白名单；这里事件文本不匹配
    assert plugin._candidate(event, KIND_SPEAK) is False
    # 其他群
    other = make_event("精华榜", group_id=10001)
    assert plugin._candidate(other, KIND_ESSENCE) is False
    # 关闭总开关
    monkeypatch.setattr(plugin, "CFG", dataclasses.replace(cfg, enabled=False))
    assert plugin._candidate(event, KIND_ESSENCE) is False


def test_candidate_requires_explicit_at(monkeypatch, cfg):
    monkeypatch.setattr(plugin, "CFG", cfg)
    assert plugin._candidate(make_event("精华榜", at=False), KIND_ESSENCE) is False


def test_essence_and_speak_whitelists_are_separate(monkeypatch, cfg):
    separate = dataclasses.replace(
        cfg, essence_groups=frozenset({GROUP}), speak_groups=frozenset({10002})
    )
    monkeypatch.setattr(plugin, "CFG", separate)
    assert plugin._candidate(make_event("精华榜"), KIND_ESSENCE) is True
    assert plugin._candidate(make_event("发言榜"), KIND_SPEAK) is False
    monkeypatch.setattr(
        plugin,
        "CFG",
        dataclasses.replace(separate, speak_groups=frozenset({GROUP})),
    )
    assert plugin._candidate(make_event("发言榜"), KIND_SPEAK) is True
    # 精华榜命令不会触发发言榜 matcher
    assert plugin._candidate(make_event("精华榜"), KIND_SPEAK) is False


def test_record_candidate(monkeypatch, cfg):
    monkeypatch.setattr(plugin, "CFG", cfg)
    assert plugin._record_candidate(make_event("随便说说")) is True
    assert plugin._record_candidate(make_event("说话", group_id=10002)) is False
    monkeypatch.setattr(plugin, "CFG", dataclasses.replace(cfg, enabled=False))
    assert plugin._record_candidate(make_event("随便说说")) is False


def test_parse_rank_command_used_by_plugin():
    request = parse_rank_command("精华榜 7")
    assert request is not None and request.days == 7


def test_lazy_db_init(monkeypatch, cfg, tmp_path):
    db_path = tmp_path / "lazy" / "rank.db"
    monkeypatch.setattr(plugin, "CFG", dataclasses.replace(cfg, db_path=str(db_path)))
    monkeypatch.setattr(plugin, "_db_state", None)
    assert plugin._db_ready() is True
    assert db_path.is_file()


def test_lazy_db_failure_degrades(monkeypatch, cfg, tmp_path):
    monkeypatch.setattr(
        plugin, "CFG", dataclasses.replace(cfg, db_path=str(tmp_path))
    )
    monkeypatch.setattr(plugin, "_db_state", None)
    assert plugin._db_ready() is False


def test_cooldown(monkeypatch, cfg):
    event = make_event("精华榜")
    monkeypatch.setattr(plugin, "CFG", dataclasses.replace(cfg, cooldown_seconds=60))
    plugin._cooldowns.clear()
    try:
        assert plugin._allow_cooldown(event) is True
        assert plugin._allow_cooldown(event) is False
    finally:
        plugin._cooldowns.clear()
    monkeypatch.setattr(plugin, "CFG", dataclasses.replace(cfg, cooldown_seconds=0))
    assert plugin._allow_cooldown(event) is True


def test_group_allowed_helpers():
    assert plugin._group_allowed("10000", frozenset({GROUP})) is True
    assert plugin._group_allowed("10002", frozenset({GROUP})) is False
    assert plugin._group_allowed(None, frozenset({GROUP})) is False
    assert plugin._essence_allowed(GROUP) is False  # 默认配置不开放任何群


def test_render_settings_from_default_config():
    assert plugin.RENDER_SETTINGS.background == ""
    assert plugin.RENDER_SETTINGS.font_dir == ""
    assert isinstance(Path("data/group_rank/group_rank.db").name, str)
