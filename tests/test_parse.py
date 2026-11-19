"""命令解析与 @bot 判定（不经过 NoneBot 事件类，纯 SimpleNamespace）。"""

from __future__ import annotations

from types import SimpleNamespace

from nonebot_plugin_group_rank.model import KIND_ESSENCE, KIND_SPEAK
from nonebot_plugin_group_rank.parse import (
    event_plaintext,
    has_at_self,
    normalize_text,
    parse_rank_command,
)


def seg(seg_type: str, **data):
    return SimpleNamespace(type=seg_type, data=data)


class FakeEvent:
    def __init__(self, text: str = "精华榜", self_id: int = 10000, at: bool = True):
        self.self_id = self_id
        segments = [seg("text", text=text)] if text else []
        self.message = segments
        self.original_message = ([seg("at", qq=str(self_id))] if at else []) + segments

    def get_plaintext(self) -> str:
        return "".join(
            str(item.data.get("text", ""))
            for item in self.message
            if item.type == "text"
        )


def test_essence_all_history():
    request = parse_rank_command("精华榜")
    assert request is not None
    assert request.kind == KIND_ESSENCE
    assert request.days is None


def test_essence_with_days():
    request = parse_rank_command(" 精华榜  7 ")
    assert request is not None
    assert request.days == 7
    assert request.kind == KIND_ESSENCE


def test_essence_without_space():
    request = parse_rank_command("精华榜7")
    assert request is not None
    assert request.days == 7


def test_essence_multiline_normalized():
    request = parse_rank_command("精华榜\n7")
    assert request is not None and request.days == 7


def test_speak_command():
    request = parse_rank_command(" 发言榜 ")
    assert request is not None
    assert request.kind == KIND_SPEAK
    assert request.days is None


def test_speak_rejects_arguments():
    assert parse_rank_command("发言榜 7") is None
    assert parse_rank_command("发言榜x") is None


def test_invalid_commands():
    assert parse_rank_command("精华榜 0") is None
    assert parse_rank_command("精华榜 7天") is None
    assert parse_rank_command("精华榜 -1") is None
    assert parse_rank_command("摸鱼榜") is None
    assert parse_rank_command("精华 榜") is None
    assert parse_rank_command("") is None
    assert parse_rank_command(None) is None


def test_normalize_text_strips_controls():
    assert normalize_text("精\x00华榜") == "精华榜"
    assert normalize_text("  精华榜 \t 7 ") == "精华榜 7"


def test_has_at_self():
    assert has_at_self(FakeEvent())
    assert not has_at_self(FakeEvent(at=False))
    other = FakeEvent(at=False)
    other.original_message = [seg("at", qq="10001")] + other.message
    assert not has_at_self(other)
    no_self = FakeEvent()
    no_self.self_id = None
    assert not has_at_self(no_self)


def test_event_plaintext():
    assert event_plaintext(FakeEvent(text="精华榜 7")) == "精华榜 7"
    assert event_plaintext(FakeEvent(text="")) == ""


def test_event_plaintext_falls_back_to_segments():
    event = SimpleNamespace(
        message=[seg("at", qq="10000"), seg("text", text="发言榜"), seg("face", id="1")]
    )
    assert event_plaintext(event) == "发言榜"


def test_event_plaintext_tolerates_broken_getter():
    def boom():
        raise RuntimeError("bad")

    event = SimpleNamespace(message=[seg("text", text="精华榜")], get_plaintext=boom)
    assert event_plaintext(event) == "精华榜"
