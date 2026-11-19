"""精华榜 / 发言榜共用图片渲染（纯 Pillow，不 import NoneBot）。

视觉沿用精华榜底版：磨砂白面板 + 顶部群信息 + Top3 领奖台 + 列表。
两种榜单只差标题与总数文案（由 :class:`RankImageMeta` 的 ``kind`` 决定）。

资源策略（都不随包分发）：

* 背景：``GROUP_RANK_BACKGROUND`` 指向的图片；缺省/读取失败时用同色系渐变。
* 字体：``GROUP_RANK_FONT_DIR`` 下的 Source Han Sans SC 四个字重；缺失时回退
  系统 DejaVu；再不行用 Pillow 内置字体保证仍能出图。
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from .config import GroupRankConfig
from .model import RankEntry, RankImageMeta, safe_initial

logger = logging.getLogger(__name__)

W, H = 1024, 1536

INK = (58, 50, 84, 255)
INK_SOFT = (108, 97, 140, 255)
INK_FAINT = (146, 136, 174, 255)
WHITE = (255, 255, 255, 255)

_FONT_ROLES = ("title", "bold", "medium", "regular")
_SOURCE_FONT_FILES = {
    "title": "SourceHanSansSC-Heavy.otf",
    "bold": "SourceHanSansSC-Bold.otf",
    "medium": "SourceHanSansSC-Medium.otf",
    "regular": "SourceHanSansSC-Regular.otf",
}
_FALLBACK_FONT_FILES = {
    "title": ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf"),
    "bold": ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf"),
    "medium": ("DejaVuSans.ttf",),
    "regular": ("DejaVuSans.ttf",),
}
_FALLBACK_FONT_DIRS = (
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/dejavu"),
    Path("/usr/share/fonts/truetype/liberation"),
    Path("/usr/share/fonts/truetype/noto"),
    Path("/usr/share/fonts/TTF"),
    Path("/usr/local/share/fonts"),
)


class RenderError(RuntimeError):
    """渲染失败（保留给调用方统一兜底）。"""


@dataclass(frozen=True, slots=True)
class RenderSettings:
    background: str = ""
    font_dir: str = ""


def settings_from_config(cfg: GroupRankConfig) -> RenderSettings:
    return RenderSettings(background=cfg.background, font_dir=cfg.font_dir)


def _font_candidates(role: str, font_dir: str):
    if font_dir:
        yield Path(font_dir) / _SOURCE_FONT_FILES[role]
    for directory in _FALLBACK_FONT_DIRS:
        for filename in _FALLBACK_FONT_FILES[role]:
            yield directory / filename


def resolve_font_paths(font_dir: str = "") -> dict[str, Path]:
    """按字重解析可用字体文件；解析不到的 role 不在返回值里。"""
    found: dict[str, Path] = {}
    for role in _FONT_ROLES:
        for candidate in _font_candidates(role, font_dir):
            try:
                if candidate.is_file():
                    found[role] = candidate
                    break
            except OSError:
                continue
    return found


def validate_assets(settings: RenderSettings | None = None) -> list[str]:
    """返回缺失的可选资源；空列表代表可以正常出图（含回退方案）。"""
    settings = settings or RenderSettings()
    missing = [
        f"font:{role}"
        for role in _FONT_ROLES
        if role not in resolve_font_paths(settings.font_dir)
    ]
    if settings.background and not Path(settings.background).is_file():
        missing.append("background")
    return missing


def _default_font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # pragma: no cover - Pillow < 10.1
        return ImageFont.load_default()


class FontBook:
    """按 (role, size) 缓存字体对象。"""

    def __init__(self, settings: RenderSettings) -> None:
        self.paths = resolve_font_paths(settings.font_dir)
        self._cache: dict[tuple[str, int], ImageFont.ImageFont] = {}

    def font(self, role: str, size: int) -> ImageFont.ImageFont:
        key = (role, int(size))
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        font: ImageFont.ImageFont | None = None
        path = self.paths.get(role)
        if path is not None:
            try:
                font = ImageFont.truetype(str(path), int(size))
            except Exception:  # noqa: BLE001 - 坏字体回退内置
                font = None
        if font is None:
            font = _default_font(int(size))
        self._cache[key] = font
        return font


def _lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def _gradient(size, top, bottom) -> Image.Image:
    width, height = size
    image = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        draw.line(
            [(0, y), (width, y)],
            fill=_lerp(top, bottom, y / max(1, height - 1)) + (255,),
        )
    return image


def _background_layer(settings: RenderSettings) -> Image.Image:
    if settings.background:
        try:
            with Image.open(settings.background) as image:
                return ImageOps.fit(
                    image.convert("RGB"), (W, H), method=Image.LANCZOS
                ).convert("RGBA")
        except Exception:  # noqa: BLE001 - 背景缺失不算错误
            logger.warning(
                "[group_rank] 背景图不可用，改用渐变: %s", settings.background
            )
    return _gradient((W, H), (240, 235, 252), (214, 226, 248))


def _fit_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    text = str(text or "").strip()
    if not text:
        return ""
    if draw.textlength(text, font=font) <= max_width:
        return text
    ellipsis = "…"
    while text and draw.textlength(text + ellipsis, font=font) > max_width:
        text = text[:-1]
    return text.rstrip() + ellipsis


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    max_width: int,
    max_lines: int = 2,
) -> list[str]:
    text = str(text or "").strip()
    if not text:
        return []
    lines: list[str] = []
    current = ""
    for char in text:
        trial = current + char
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
            continue
        if current:
            lines.append(current)
            current = char
        else:
            lines.append(char)
        if len(lines) >= max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    consumed = sum(len(line) for line in lines)
    if consumed < len(text) and lines:
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > max_width:
            last = last[:-1]
        lines[-1] = last + "…"
    return lines


def _circular(
    image: Image.Image, size: int, ring=None, ring_width: int = 5
) -> Image.Image:
    image = ImageOps.fit(image.convert("RGB"), (size, size), method=Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(image, (0, 0), mask)
    if ring:
        draw = ImageDraw.Draw(out)
        draw.ellipse(
            (
                ring_width // 2,
                ring_width // 2,
                size - 1 - ring_width // 2,
                size - 1 - ring_width // 2,
            ),
            outline=ring,
            width=ring_width,
        )
    return out


def _placeholder_avatar(
    initial: str, seed: int, size: int, ring, book: FontBook
) -> Image.Image:
    palettes = [
        ((255, 216, 200), (255, 150, 176)),
        ((204, 190, 255), (137, 168, 255)),
        ((196, 240, 225), (137, 211, 255)),
        ((255, 228, 218), (255, 168, 200)),
        ((222, 208, 255), (157, 187, 255)),
        ((255, 226, 182), (255, 172, 126)),
    ]
    top, bottom = palettes[seed % len(palettes)]
    image = _gradient((size, size), top, bottom)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(image, (0, 0), mask)
    draw = ImageDraw.Draw(out)
    font = book.font("title", int(size * 0.40))
    glyph = (initial or "♪")[0]
    bbox = draw.textbbox((0, 0), glyph, font=font)
    draw.text(
        (
            (size - (bbox[2] - bbox[0])) / 2 - bbox[0],
            (size - (bbox[3] - bbox[1])) / 2 - bbox[1],
        ),
        glyph,
        font=font,
        fill=WHITE,
    )
    if ring:
        draw.ellipse((3, 3, size - 4, size - 4), outline=ring, width=5)
    return out


def _avatar(
    data: bytes | None,
    user_id: int,
    name: str,
    size: int,
    ring,
    book: FontBook,
) -> Image.Image:
    if data:
        try:
            return _circular(
                Image.open(BytesIO(data)),
                size,
                ring=ring,
                ring_width=5 if ring else 4,
            )
        except Exception:  # noqa: BLE001 - 坏图走占位
            pass
    return _placeholder_avatar(safe_initial(name), user_id, size, ring, book)


def _draw_count(
    draw: ImageDraw.ImageDraw,
    center_x: int,
    center_y: int,
    value: int,
    number_size: int,
    unit_size: int,
    book: FontBook,
) -> None:
    number = str(value)
    unit = " 条"
    number_font = book.font("title", number_size)
    unit_font = book.font("medium", unit_size)
    number_width = draw.textlength(number, font=number_font)
    unit_width = draw.textlength(unit, font=unit_font)
    start = center_x - (number_width + unit_width) / 2
    draw.text((start, center_y), number, font=number_font, fill=INK, anchor="lm")
    draw.text(
        (start + number_width, center_y),
        unit,
        font=unit_font,
        fill=INK_SOFT,
        anchor="lm",
    )


def _draw_star(
    draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int, color
) -> None:
    points = []
    for index in range(8):
        angle = -math.pi / 2 + index * math.pi / 4
        r = radius if index % 2 == 0 else radius * 0.30
        points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    draw.polygon(points, fill=color)


def _draw_header(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    meta: RankImageMeta,
    group_avatar: bytes | None,
    book: FontBook,
) -> None:
    draw.text(
        (W / 2, 106),
        meta.title,
        font=book.font("title", 76),
        fill=INK,
        anchor="mm",
    )

    group_label = f"{meta.group_name}  ·  {meta.mode_label}  ·  {meta.total_label}"
    label_font = book.font("bold", 24)
    group_label = _fit_text(draw, group_label, label_font, 790)
    label_width = draw.textlength(group_label, font=label_font)
    row_width = 56 + 14 + label_width
    row_x = (W - row_width) / 2
    row_cy = 190
    avatar = _avatar(group_avatar, 0, "群", 56, (255, 255, 255, 235), book)
    canvas.alpha_composite(avatar, (int(row_x), int(row_cy - 28)))
    draw.text(
        (row_x + 70, row_cy), group_label, font=label_font, fill=INK_SOFT, anchor="lm"
    )

    _draw_star(draw, 116, 105, 11, (255, 255, 255, 185))
    _draw_star(draw, 904, 92, 9, (255, 255, 255, 175))
    _draw_star(draw, 950, 188, 6, (255, 236, 186, 200))
    draw.line((422, 240, 602, 240), fill=(212, 183, 130, 145), width=2)
    _draw_star(draw, 408, 240, 7, (240, 205, 140, 220))


def _draw_podium(
    canvas: Image.Image,
    entries: list[RankEntry],
    avatars: dict[int, bytes | None],
    book: FontBook,
) -> None:
    rings = {1: (236, 188, 102, 255), 2: (186, 196, 218, 255), 3: (208, 158, 121, 255)}
    tints = {1: (255, 248, 226, 218), 2: (246, 249, 255, 210), 3: (253, 242, 234, 210)}
    outlines = {1: (244, 206, 134, 235), 2: (208, 216, 232, 225), 3: (232, 190, 160, 225)}
    geometry = [
        {"rank": 2, "box": (92, 380, 344, 680), "avatar": 108, "entry": entries[1]},
        {"rank": 1, "box": (368, 312, 656, 680), "avatar": 132, "entry": entries[0]},
        {"rank": 3, "box": (680, 380, 932, 680), "avatar": 108, "entry": entries[2]},
    ]
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    def count_center_y(rank: int, name_top: int, lines: int) -> int:
        line_h = 38 if rank == 1 else 29
        return name_top + lines * line_h + (22 if rank == 1 else 18)

    for item in geometry:
        rank = item["rank"]
        x1, y1, x2, y2 = item["box"]
        entry = item["entry"]
        draw.rounded_rectangle(
            (x1, y1, x2, y2),
            radius=30,
            fill=tints[rank],
            outline=outlines[rank],
            width=2,
        )
        badge_radius = 21 if rank == 1 else 18
        badge_x, badge_y = x1 + 34, y1 + 36
        badge_fill = {
            1: (239, 187, 91, 255),
            2: (176, 188, 210, 255),
            3: (202, 148, 111, 255),
        }[rank]
        draw.ellipse(
            (
                badge_x - badge_radius,
                badge_y - badge_radius,
                badge_x + badge_radius,
                badge_y + badge_radius,
            ),
            fill=badge_fill,
        )
        draw.text(
            (badge_x, badge_y + 1),
            str(rank),
            font=book.font("title", 22 if rank == 1 else 20),
            fill=WHITE,
            anchor="mm",
        )

        avatar_size = item["avatar"]
        avatar = _avatar(
            avatars.get(entry.user_id),
            entry.user_id,
            entry.name,
            avatar_size,
            rings[rank],
            book,
        )
        avatar_cx = (x1 + x2) / 2
        avatar_top = y1 + (74 if rank == 1 else 66)
        layer.alpha_composite(
            avatar, (int(avatar_cx - avatar_size / 2), int(avatar_top))
        )

        name_font = book.font("bold", 29 if rank == 1 else 23)
        name_width = (x2 - x1) - 36
        lines = _wrap_text(draw, entry.name, name_font, name_width, max_lines=2)
        line_h = 38 if rank == 1 else 29
        name_top = avatar_top + avatar_size + (14 if rank == 1 else 12)
        for line_index, line in enumerate(lines):
            draw.text(
                (avatar_cx, name_top + line_index * line_h),
                line,
                font=name_font,
                fill=INK,
                anchor="ma",
            )
        count_y = count_center_y(rank, name_top, len(lines))
        _draw_count(
            draw,
            int(avatar_cx),
            min(count_y, y2 - 30),
            entry.count,
            number_size=38 if rank == 1 else 32,
            unit_size=18 if rank == 1 else 16,
            book=book,
        )

    canvas.alpha_composite(layer)


def _draw_list_rows(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    entries: list[RankEntry],
    avatars: dict[int, bytes | None],
    max_count: int,
    book: FontBook,
) -> None:
    row_top = 720
    row_h = 92
    inner_left, inner_right = 116, 908
    bar_left, bar_right = 240, 800

    for index in range(3, len(entries)):
        entry = entries[index]
        rank = index + 1
        center_y = row_top + (index - 3) * row_h + row_h / 2

        badge_cx = inner_left + 18
        draw.ellipse(
            (badge_cx - 18, center_y - 18, badge_cx + 18, center_y + 18),
            fill=(255, 255, 255, 156),
            outline=(167, 154, 198, 155),
            width=1,
        )
        draw.text(
            (badge_cx, center_y + 1),
            str(rank),
            font=book.font("bold", 18),
            fill=INK_SOFT,
            anchor="mm",
        )

        avatar_size = 58
        avatar = _avatar(
            avatars.get(entry.user_id), entry.user_id, entry.name, avatar_size, None, book
        )
        canvas.alpha_composite(avatar, (164, int(center_y - avatar_size / 2)))

        name_font = book.font("bold", 25)
        name = _fit_text(draw, entry.name, name_font, 340)
        draw.text((240, center_y - 17), name, font=name_font, fill=INK, anchor="lm")

        track_y = center_y + 16
        draw.rounded_rectangle(
            (bar_left, track_y - 4, bar_right, track_y + 4),
            radius=4,
            fill=(227, 221, 242, 170),
        )
        bar_width = max(
            10, int((bar_right - bar_left) * entry.count / max(1, max_count))
        )
        draw.rounded_rectangle(
            (bar_left, track_y - 4, bar_left + bar_width, track_y + 4),
            radius=4,
            fill=(151, 133, 221, 205),
        )
        draw.ellipse(
            (bar_left + bar_width - 3, track_y - 7, bar_left + bar_width + 3, track_y + 7),
            fill=(255, 255, 255, 225),
        )
        draw.text(
            (inner_right, center_y - 1),
            f"{entry.count} 条",
            font=book.font("medium", 23),
            fill=INK_SOFT,
            anchor="rm",
        )

        if index < len(entries) - 1:
            line_y = row_top + (index - 3) * row_h + row_h
            draw.line(
                (inner_left, line_y, inner_right, line_y),
                fill=(140, 126, 175, 24),
                width=1,
            )


def _draw_compact(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    entries: list[RankEntry],
    avatars: dict[int, bytes | None],
    book: FontBook,
) -> None:
    count = len(entries)
    card_width = 760
    card_height = 176 if count == 1 else 150
    gap = 24
    total_height = count * card_height + (count - 1) * gap
    top = (272 + 1420) / 2 - total_height / 2
    left = (W - card_width) / 2
    max_count = max(entry.count for entry in entries)

    for index, entry in enumerate(entries):
        y1 = top + index * (card_height + gap)
        y2 = y1 + card_height
        center_y = (y1 + y2) / 2
        draw.rounded_rectangle(
            (left, y1, left + card_width, y2),
            radius=30,
            fill=(255, 252, 244, 212) if index == 0 else (255, 255, 255, 196),
            outline=(238, 210, 156, 220) if index == 0 else (208, 200, 230, 190),
            width=2,
        )
        badge_cx = left + 38
        draw.ellipse(
            (badge_cx - 20, center_y - 20, badge_cx + 20, center_y + 20),
            fill=(239, 187, 91, 255) if index == 0 else (255, 255, 255, 170),
            outline=(239, 187, 91, 255) if index == 0 else (167, 154, 198, 155),
            width=1,
        )
        draw.text(
            (badge_cx, center_y + 1),
            str(index + 1),
            font=book.font("title", 20),
            fill=WHITE if index == 0 else INK_SOFT,
            anchor="mm",
        )

        avatar_size = 96 if count == 1 else 84
        avatar = _avatar(
            avatars.get(entry.user_id), entry.user_id, entry.name, avatar_size, None, book
        )
        avatar_x = left + 78
        canvas.alpha_composite(
            avatar, (int(avatar_x), int(center_y - avatar_size / 2))
        )

        name_x = avatar_x + avatar_size + 26
        name_font = book.font("bold", 30 if count == 1 else 27)
        name = _fit_text(draw, entry.name, name_font, 410)
        draw.text((name_x, center_y - 18), name, font=name_font, fill=INK, anchor="lm")

        bar_left, bar_right = name_x, left + card_width - 150
        track_y = center_y + 18
        draw.rounded_rectangle(
            (bar_left, track_y - 4, bar_right, track_y + 4),
            radius=4,
            fill=(227, 221, 242, 170),
        )
        bar_width = max(
            10, int((bar_right - bar_left) * entry.count / max(1, max_count))
        )
        draw.rounded_rectangle(
            (bar_left, track_y - 4, bar_left + bar_width, track_y + 4),
            radius=4,
            fill=(151, 133, 221, 205),
        )
        _draw_count(
            draw,
            int(left + card_width - 78),
            int(center_y),
            entry.count,
            number_size=34 if count == 1 else 30,
            unit_size=17 if count == 1 else 16,
            book=book,
        )


def render_image(
    meta: RankImageMeta,
    avatars: dict[int, bytes | None] | None = None,
    group_avatar: bytes | None = None,
    settings: RenderSettings | None = None,
) -> bytes:
    """把榜单渲染成 1024×1536 PNG 字节。"""
    settings = settings or RenderSettings()
    book = FontBook(settings)
    avatars = avatars or {}

    canvas = _background_layer(settings)

    veil = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    veil_draw = ImageDraw.Draw(veil)
    for y in range(0, 390):
        veil_draw.line(
            [(0, y), (W, y)],
            fill=(255, 255, 255, int(95 * (1 - y / 390) ** 1.5)),
        )
    for y in range(H - 170, H):
        veil_draw.line(
            [(0, y), (W, y)],
            fill=(255, 255, 255, int(100 * ((y - (H - 170)) / 170) ** 1.4)),
        )
    canvas = Image.alpha_composite(canvas, veil)

    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (52, 292, 972, 1440), radius=56, fill=(66, 50, 103, 74)
    )
    canvas = Image.alpha_composite(
        canvas, shadow.filter(ImageFilter.GaussianBlur(28))
    )

    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle(
        (56, 272, 968, 1420),
        radius=50,
        fill=(255, 255, 255, 198),
        outline=(255, 255, 255, 235),
        width=2,
    )
    canvas = Image.alpha_composite(canvas, panel)
    draw = ImageDraw.Draw(canvas)

    entries = list(meta.entries[:10])
    _draw_header(canvas, draw, meta, group_avatar, book)

    if len(entries) >= 3:
        _draw_podium(canvas, entries, avatars, book)
        draw = ImageDraw.Draw(canvas)  # podium 用了独立图层
        _draw_list_rows(canvas, draw, entries, avatars, entries[0].count, book)
    elif entries:
        _draw_compact(canvas, draw, entries, avatars, book)
    else:
        draw.text(
            (W / 2, 760),
            "暂无上榜数据",
            font=book.font("medium", 34),
            fill=INK_FAINT,
            anchor="mm",
        )

    output = BytesIO()
    canvas.convert("RGB").save(output, "PNG", optimize=True)
    return output.getvalue()


__all__ = [
    "FontBook",
    "RenderError",
    "RenderSettings",
    "render_image",
    "resolve_font_paths",
    "settings_from_config",
    "validate_assets",
]
