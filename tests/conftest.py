"""pytest 公共夹具。

- 先 ``nonebot.init()``，再让测试 import 插件包（插件 __init__ 需要 driver）。
- autouse fixture 清掉 ``GROUP_RANK_*`` 环境变量，保证默认值断言不受外部环境影响。
- 不连 NapCat：所有 API 调用都走 :class:`FakeBot`。
"""

from __future__ import annotations

import os
from dataclasses import replace

import nonebot
import pytest

nonebot.init()

_ENV_PREFIX = "GROUP_RANK_"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch):
    for key in list(os.environ):
        if key.startswith(_ENV_PREFIX):
            monkeypatch.delenv(key, raising=False)
    yield


@pytest.fixture
def cfg(tmp_path):
    """打开两个榜单、群白名单只有 10000、数据落在 tmp_path 的配置。"""
    from nonebot_plugin_group_rank.config import load_config

    return replace(
        load_config(),
        enabled=True,
        essence_groups=frozenset({10000}),
        speak_groups=frozenset({10000}),
        db_path=str(tmp_path / "group_rank.db"),
        avatar_cache_dir=str(tmp_path / "avatars"),
    )


class FakeBot:
    """只实现 call_api 的假 bot；responses 的值可以是异常实例。"""

    self_id = "10000"

    def __init__(self, responses: dict[str, object] | None = None) -> None:
        self.responses = dict(responses or {})
        self.calls: list[tuple[str, dict]] = []

    async def call_api(self, api: str, **kwargs):
        self.calls.append((api, kwargs))
        value = self.responses.get(api)
        if isinstance(value, BaseException):
            raise value
        return value


@pytest.fixture
def fake_bot():
    def _make(responses: dict[str, object] | None = None) -> FakeBot:
        return FakeBot(responses)

    return _make
