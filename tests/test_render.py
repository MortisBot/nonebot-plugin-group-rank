"""渲染：1/3/10 行、无背景、系统 DejaVu 字体、两种榜单标题。"""

from __future__ import annotations

from io import BytesIO

import pytest
from nonebot_plugin_group_rank import render
from nonebot_plugin_group_rank.model import (
    KIND_ESSENCE,
    KIND_SPEAK,
    RankEntry,
    RankImageMeta,
)
from PIL import Image


def _meta(kind: str, count: int, *, name_prefix: str = "user") -> RankImageMeta:
    entries = tuple(
        RankEntry(
            user_id=10000 + index,
            name=f"{name_prefix}{index + 1}",
            count=max(1, 12 - index),
        )
        for index in range(count)
    )
    return RankImageMeta(
        kind=kind,
        group_name="test-group",
        mode_label="全部历史" if kind == KIND_ESSENCE else "近 24 小时",
        total=sum(entry.count for entry in entries),
        entries=entries,
    )


def test_font_fallback_available():
    if not render.resolve_font_paths():
        pytest.skip("系统没有可回退字体")
    assert render.resolve_font_paths()["title"].is_file()
    assert render.validate_assets() == []


@pytest.mark.parametrize("count", [1, 2, 3, 10])
def test_render_essence_rows(tmp_path, count):
    png = render.render_image(_meta(KIND_ESSENCE, count))
    path = tmp_path / f"essence_{count}.png"
    path.write_bytes(png)
    assert len(png) > 10_000
    with Image.open(BytesIO(png)) as image:
        assert image.size == (1024, 1536)
        image.verify()


@pytest.mark.parametrize("count", [1, 3, 10])
def test_render_speak_rows(tmp_path, count):
    png = render.render_image(_meta(KIND_SPEAK, count, name_prefix="speaker"))
    assert len(png) > 10_000
    with Image.open(BytesIO(png)) as image:
        assert image.size == (1024, 1536)
        image.verify()


def test_render_with_avatars_and_missing_bytes():
    entries = _meta(KIND_ESSENCE, 3).entries
    meta = RankImageMeta(
        kind=KIND_ESSENCE,
        group_name="test-group",
        mode_label="近 7 天",
        total=sum(entry.count for entry in entries),
        entries=entries,
    )
    avatars = {entries[0].user_id: b"not-an-image", entries[1].user_id: None}
    png = render.render_image(meta, avatars, b"broken", render.RenderSettings())
    assert len(png) > 10_000


def test_render_empty_entries():
    meta = RankImageMeta(
        kind=KIND_SPEAK,
        group_name="test-group",
        mode_label="近 24 小时",
        total=0,
        entries=(),
    )
    png = render.render_image(meta)
    assert len(png) > 5_000
    with Image.open(BytesIO(png)) as image:
        assert image.size == (1024, 1536)


def test_missing_background_falls_back(tmp_path):
    settings = render.RenderSettings(background=str(tmp_path / "nope.jpg"))
    assert "background" in render.validate_assets(settings)
    png = render.render_image(_meta(KIND_ESSENCE, 3), settings=settings)
    assert len(png) > 10_000


def test_background_image_is_used(tmp_path):
    background = tmp_path / "bg.png"
    Image.new("RGB", (64, 96), (30, 120, 200)).save(background)
    settings = render.RenderSettings(background=str(background))
    assert render.validate_assets(settings) == []
    png = render.render_image(_meta(KIND_SPEAK, 1), settings=settings)
    assert len(png) > 10_000


def test_font_dir_missing_falls_back(tmp_path):
    settings = render.RenderSettings(font_dir=str(tmp_path / "fonts"))
    if not render.resolve_font_paths():
        pytest.skip("系统没有可回退字体")
    png = render.render_image(_meta(KIND_ESSENCE, 2), settings=settings)
    assert len(png) > 10_000


def test_title_adaptation():
    essence = _meta(KIND_ESSENCE, 1)
    speak = _meta(KIND_SPEAK, 1)
    assert essence.title == "群精华榜"
    assert speak.title == "群发言榜"
    assert essence.total_label.startswith("当前在库 ")
    assert speak.total_label.startswith("发言 ")
