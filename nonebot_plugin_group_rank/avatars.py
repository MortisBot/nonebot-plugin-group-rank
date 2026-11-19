"""榜单头像下载与文件缓存。

QQ 头像优先；不可用/纯黑时用首字占位，绝不阻塞出图。
"""

from __future__ import annotations

import asyncio
import time
from io import BytesIO
from pathlib import Path

import httpx
from nonebot import logger
from PIL import Image, ImageStat

from .config import GroupRankConfig

AVATAR_TIMEOUT = 10.0
AVATAR_CONCURRENCY = 4
_QQ_HEAD = "https://q.qlogo.cn/g?b=qq&nk={uid}&s=640"
_GROUP_MEMBER_HEAD = "https://p.qlogo.cn/gh/{gid}/{uid}/640"
_GROUP_HEAD = "https://p.qlogo.cn/gh/{gid}/{gid}/640"


def _cache_path(root: Path, group_id: int, user_id: int) -> Path:
    return root / f"u_{group_id}_{user_id}.img"


def _group_cache_path(root: Path, group_id: int) -> Path:
    return root / f"g_{group_id}.img"


def _image_ok(data: bytes, *, reject_flat: bool = True) -> bool:
    try:
        image = Image.open(BytesIO(data)).convert("RGB").resize((32, 32), Image.LANCZOS)
        if reject_flat:
            stats = ImageStat.Stat(image)
            if max(stats.stddev) < 5.0:
                return False
        return True
    except Exception:  # noqa: BLE001 - 坏图直接当没有
        return False


def _is_fresh(path: Path, ttl_seconds: float) -> bool:
    try:
        if not path.is_file() or path.stat().st_size < 100:
            return False
        return ttl_seconds <= 0 or (time.time() - path.stat().st_mtime) <= ttl_seconds
    except OSError:
        return False


def _read_cache(path: Path, ttl_seconds: float) -> bytes | None:
    if not _is_fresh(path, ttl_seconds):
        return None
    try:
        data = path.read_bytes()
        return data if _image_ok(data) else None
    except OSError:
        return None


def _write_cache(path: Path, data: bytes) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    except OSError:
        logger.debug("[group_rank] avatar cache write failed path={}", path)


def _prune_cache(root: Path, ttl_days: float, max_files: int) -> None:
    try:
        root.mkdir(parents=True, exist_ok=True)
        files = [path for path in root.glob("*.img") if path.is_file()]
        now = time.time()
        ttl = max(0.0, ttl_days) * 86400.0
        for path in files:
            try:
                if ttl > 0 and now - path.stat().st_mtime > ttl:
                    path.unlink(missing_ok=True)
            except OSError:
                pass
        files = [path for path in root.glob("*.img") if path.is_file()]
        if len(files) > max_files:
            files.sort(key=lambda path: path.stat().st_mtime)
            for path in files[: len(files) - max_files]:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
    except OSError:
        logger.warning("[group_rank] avatar cache dir unavailable: {}", root)


async def _get_image(client: httpx.AsyncClient, url: str) -> bytes | None:
    try:
        response = await client.get(url)
        if response.status_code == 200 and response.content:
            return response.content
    except Exception:  # noqa: BLE001 - 头像失败不影响出图
        pass
    return None


async def _fetch_user_avatar(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    root: Path,
    group_id: int,
    user_id: int,
    ttl_seconds: float,
) -> bytes | None:
    path = _cache_path(root, group_id, user_id)
    cached = _read_cache(path, ttl_seconds)
    if cached is not None:
        return cached

    async with sem:
        data = await _get_image(client, _QQ_HEAD.format(uid=user_id))
        if data and _image_ok(data):
            _write_cache(path, data)
            return data
        if data and _image_ok(data, reject_flat=False):
            # 纯色/纯黑头像：直接用占位，避免黑块。
            return None
        fallback = await _get_image(
            client, _GROUP_MEMBER_HEAD.format(gid=group_id, uid=user_id)
        )
        if fallback and _image_ok(fallback):
            _write_cache(path, fallback)
            return fallback
    return None


async def _fetch_group_avatar(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    root: Path,
    group_id: int,
    ttl_seconds: float,
) -> bytes | None:
    path = _group_cache_path(root, group_id)
    cached = _read_cache(path, ttl_seconds)
    if cached is not None:
        return cached
    async with sem:
        data = await _get_image(client, _GROUP_HEAD.format(gid=group_id))
        if data and _image_ok(data):
            _write_cache(path, data)
            return data
    return None


async def collect_avatars(
    group_id: int,
    user_ids: list[int],
    cfg: GroupRankConfig,
) -> tuple[dict[int, bytes | None], bytes | None]:
    """并发拉取用户头像和群头像；任何失败都降级为 None。"""
    root = Path(cfg.avatar_cache_dir)
    ttl_seconds = max(0.0, cfg.avatar_ttl_days) * 86400.0
    await asyncio.to_thread(
        _prune_cache, root, cfg.avatar_ttl_days, cfg.avatar_max_files
    )

    sem = asyncio.Semaphore(AVATAR_CONCURRENCY)
    unique_ids = list(dict.fromkeys(int(uid) for uid in user_ids if int(uid) > 0))
    try:
        async with httpx.AsyncClient(
            timeout=AVATAR_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as client:
            group_task = asyncio.create_task(
                _fetch_group_avatar(client, sem, root, group_id, ttl_seconds)
            )
            user_tasks = [
                asyncio.create_task(
                    _fetch_user_avatar(client, sem, root, group_id, uid, ttl_seconds)
                )
                for uid in unique_ids
            ]
            group_avatar, *user_results = await asyncio.gather(
                group_task, *user_tasks, return_exceptions=True
            )
    except Exception:  # noqa: BLE001 - 头像整体失败也照常出图
        logger.warning("[group_rank] avatar fetch failed group={}", group_id)
        return {}, None

    avatars: dict[int, bytes | None] = {}
    for uid, result in zip(unique_ids, user_results, strict=False):
        avatars[uid] = result if isinstance(result, bytes) else None
    group_bytes = group_avatar if isinstance(group_avatar, bytes) else None
    return avatars, group_bytes


__all__ = ["collect_avatars"]
