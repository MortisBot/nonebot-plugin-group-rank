"""群精华榜 / 群发言榜（OneBot v11，需 NapCat）。

命令（必须 @bot，且群在对应白名单里）：

    @bot 精华榜       当前在库的全部精华（NapCat 实时拉取，不落库）
    @bot 精华榜 7     近 7×24 小时被设为精华的
    @bot 发言榜       ``GROUP_RANK_WINDOW_SECONDS`` 窗口内的发言次数

发言榜把消息元数据（群/用户/消息 id/时间）写本地 SQLite；新群第一次出榜时用
``get_group_msg_history`` 回填最近的消息（上限 1000 条），不存消息内容。
"""

from __future__ import annotations

import asyncio
import base64
import time

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import (
    Bot,
    Event,
    GroupMessageEvent,
    Message,
    MessageSegment,
)
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule

from . import store
from .avatars import collect_avatars
from .config import GroupRankConfig, load_config
from .essence import collect_essence_meta
from .history import backfill_group
from .members import fetch_group_name, fetch_member_infos
from .model import (
    KIND_ESSENCE,
    KIND_SPEAK,
    RankDataError,
    RankImageMeta,
    safe_group_name,
)
from .parse import event_plaintext, has_at_self, parse_rank_command
from .ranking import build_speak_meta, select_speak_entries, window_label
from .render import (
    RenderError,
    RenderSettings,
    render_image,
    settings_from_config,
    validate_assets,
)

__plugin_meta__ = PluginMetadata(
    name="group-rank",
    description=(
        "生成群精华榜 / 群发言榜图片；精华榜实时读 NapCat，发言榜用本地 SQLite "
        "统计并可回填历史（不存消息内容）。"
    ),
    usage=(
        "@bot 精华榜      全部历史（当前在库）\n"
        "@bot 精华榜 7    近 7×24 小时被设为精华的\n"
        "@bot 发言榜      配置窗口内的发言次数榜"
    ),
    type="application",
    homepage="https://github.com/MortisBot/nonebot-plugin-group-rank",
    supported_adapters={"~onebot.v11"},
)

CFG: GroupRankConfig = load_config()
RENDER_SETTINGS: RenderSettings = settings_from_config(CFG)
_missing_assets = validate_assets(RENDER_SETTINGS)
if _missing_assets:
    logger.warning(
        "[group_rank] 可选资源缺失（已回退）: {}", ", ".join(_missing_assets)
    )

_render_semaphore = asyncio.Semaphore(1)
_cooldowns: dict[tuple[int, int], float] = {}
_insert_counts: dict[int, int] = {}
_backfill_locks: dict[int, asyncio.Lock] = {}
_backfill_fail_until: dict[int, float] = {}
_db_state: bool | None = None


def _db_ready() -> bool:
    """首次用到数据库时才初始化，避免禁用状态下产生数据目录。"""
    global _db_state
    if _db_state is None:
        _db_state = store.try_init_db(CFG.db_path)
    return _db_state


def _group_allowed(group_id: object, groups: frozenset[int]) -> bool:
    try:
        return int(group_id) in groups
    except (TypeError, ValueError):
        return False


def _essence_allowed(group_id: object) -> bool:
    return _group_allowed(group_id, CFG.essence_groups)


def _speak_allowed(group_id: object) -> bool:
    return _group_allowed(group_id, CFG.speak_groups)


def _candidate(event: Event, kind: str) -> bool:
    try:
        if not CFG.enabled or not isinstance(event, GroupMessageEvent):
            return False
        allowed = _essence_allowed if kind == KIND_ESSENCE else _speak_allowed
        if not allowed(event.group_id):
            return False
        if not has_at_self(event):
            return False
        request = parse_rank_command(event_plaintext(event))
        return request is not None and request.kind == kind
    except Exception:  # noqa: BLE001 - 规则异常不能拖垮事件分发
        logger.exception("[group_rank] 命令匹配规则异常")
        return False


essence_matcher = on_message(
    rule=Rule(lambda event: _candidate(event, KIND_ESSENCE)), priority=6, block=True
)
speak_matcher = on_message(
    rule=Rule(lambda event: _candidate(event, KIND_SPEAK)), priority=6, block=True
)


def _record_candidate(event: Event) -> bool:
    return (
        CFG.enabled
        and isinstance(event, GroupMessageEvent)
        and _speak_allowed(event.group_id)
    )


record_matcher = on_message(rule=Rule(_record_candidate), priority=99, block=False)


def _allow_cooldown(event: GroupMessageEvent) -> bool:
    now = time.monotonic()
    key = (int(event.group_id), int(event.user_id))
    last = _cooldowns.get(key)
    if last is not None and now - last < CFG.cooldown_seconds:
        return False
    _cooldowns[key] = now
    if len(_cooldowns) > 1024:
        cutoff = now - max(60.0, CFG.cooldown_seconds * 6)
        for item_key, last_time in list(_cooldowns.items()):
            if last_time < cutoff:
                _cooldowns.pop(item_key, None)
    return True


def _backfill_lock(group_id: int) -> asyncio.Lock:
    lock = _backfill_locks.get(group_id)
    if lock is None:
        lock = asyncio.Lock()
        _backfill_locks[group_id] = lock
    return lock


async def _ensure_backfill(bot: Bot, group_id: int) -> None:
    if not _db_ready():
        return
    try:
        done = await asyncio.to_thread(store.is_backfilled, CFG.db_path, group_id)
    except Exception:  # noqa: BLE001 - 读 marker 失败就当没回填过
        done = False
    if done or time.monotonic() < _backfill_fail_until.get(group_id, 0.0):
        return
    async with _backfill_lock(group_id):
        try:
            done = await asyncio.to_thread(
                store.is_backfilled, CFG.db_path, group_id
            )
        except Exception:  # noqa: BLE001
            done = False
        if done:
            return
        try:
            rows = await backfill_group(bot, group_id, CFG)
            await asyncio.to_thread(
                store.mark_backfilled, CFG.db_path, group_id
            )
            logger.info(
                "[group_rank] backfill done group={} rows={}", group_id, rows
            )
        except Exception as exc:  # noqa: BLE001 - 回填失败不影响在线统计
            _backfill_fail_until[group_id] = time.monotonic() + 300.0
            logger.warning(
                "[group_rank] backfill failed group={} err={}: {}",
                group_id,
                type(exc).__name__,
                exc,
            )


def _image_message(png: bytes) -> Message:
    encoded = base64.b64encode(png).decode("ascii")
    return Message(MessageSegment.image("base64://" + encoded))


@record_matcher.handle()
async def _record_message(bot: Bot, event: GroupMessageEvent) -> None:
    if not CFG.enabled or not _db_ready():
        return
    group_id = int(event.group_id)
    if not _speak_allowed(group_id):
        return
    user_id = int(event.user_id)
    if user_id == int(event.self_id):
        return
    message_id = getattr(event, "message_id", None)
    if message_id is None:
        return
    ts = int(getattr(event, "time", 0) or time.time())
    try:
        inserted = await asyncio.to_thread(
            store.add_message, CFG.db_path, group_id, user_id, message_id, ts
        )
    except Exception:  # noqa: BLE001 - 写库失败不能影响聊天
        logger.debug(
            "[group_rank] record failed group={} user={}", group_id, user_id
        )
        return
    if not inserted:
        return
    counter = _insert_counts.get(group_id, 0) + 1
    _insert_counts[group_id] = counter
    if counter % 200 == 0:
        try:
            await asyncio.to_thread(
                store.prune_before,
                CFG.db_path,
                int(time.time()) - CFG.window_seconds - 3600,
            )
        except Exception:  # noqa: BLE001 - 清理失败下轮再说
            pass


@essence_matcher.handle()
async def _handle_essence(bot: Bot, event: GroupMessageEvent) -> None:
    request = parse_rank_command(event_plaintext(event))
    if request is None or request.kind != KIND_ESSENCE:
        return
    if not _allow_cooldown(event):
        return
    group_id = int(event.group_id)
    payload: Message | str | None = None
    try:
        async with _render_semaphore:
            meta: RankImageMeta = await collect_essence_meta(
                bot, group_id, request.days, CFG
            )
            if not meta.entries:
                if request.days is None:
                    payload = "当前没有可展示的精华数据"
                else:
                    payload = f"近 {request.days} 天暂无新增精华"
            else:
                user_ids = [entry.user_id for entry in meta.entries]
                avatars, group_avatar = await collect_avatars(
                    group_id, user_ids, CFG
                )
                png = await asyncio.to_thread(
                    render_image, meta, avatars, group_avatar, RENDER_SETTINGS
                )
                payload = _image_message(png)
    except RankDataError:
        logger.warning("[group_rank] 获取精华数据失败 group={}", group_id)
        payload = "获取精华数据失败，请稍后再试"
    except RenderError:
        logger.exception("[group_rank] 渲染失败 group={}", group_id)
        payload = "图片生成失败，请稍后再试"
    except Exception:  # noqa: BLE001 - 兜底出文案而不是静默失败
        logger.exception("[group_rank] 生成精华榜异常 group={}", group_id)
        payload = "图片生成失败，请稍后再试"

    if payload is not None:
        await essence_matcher.finish(payload)


@speak_matcher.handle()
async def _handle_speak(bot: Bot, event: GroupMessageEvent) -> None:
    if not _allow_cooldown(event):
        return
    group_id = int(event.group_id)
    label = window_label(CFG.window_seconds)
    payload: Message | str | None = None
    try:
        if not _db_ready():
            payload = "发言榜数据暂不可用，请稍后再试"
        else:
            await _ensure_backfill(bot, group_id)
            since = int(time.time()) - CFG.window_seconds
            counts = await asyncio.to_thread(
                store.counts_since, CFG.db_path, group_id, since
            )
            if not counts:
                payload = f"{label}暂无发言记录"
            else:
                infos = await fetch_member_infos(
                    bot, group_id, [uid for uid, _ in counts], CFG
                )
                entries, total = select_speak_entries(
                    counts,
                    infos,
                    self_id=int(bot.self_id),
                    top_n=CFG.top_n,
                )
                if not entries:
                    payload = f"{label}暂无发言记录"
                else:
                    group_name = await fetch_group_name(bot, group_id)
                    meta = build_speak_meta(
                        entries,
                        total=total,
                        window_seconds=CFG.window_seconds,
                        group_id=group_id,
                        group_name=safe_group_name(group_name, group_id),
                    )
                    avatars, group_avatar = await collect_avatars(
                        group_id, [entry.user_id for entry in entries], CFG
                    )
                    async with _render_semaphore:
                        png = await asyncio.to_thread(
                            render_image,
                            meta,
                            avatars,
                            group_avatar,
                            RENDER_SETTINGS,
                        )
                    payload = _image_message(png)
    except RenderError:
        logger.exception("[group_rank] 渲染失败 group={}", group_id)
        payload = "图片生成失败，请稍后再试"
    except Exception:  # noqa: BLE001 - 兜底出文案而不是静默失败
        logger.exception("[group_rank] 生成发言榜异常 group={}", group_id)
        payload = "发言榜生成失败，请稍后再试"

    if payload is not None:
        await speak_matcher.finish(payload)


__all__ = ["CFG", "RENDER_SETTINGS"]
