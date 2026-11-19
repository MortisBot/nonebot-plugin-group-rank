# nonebot-plugin-group-rank

_✨ 生成群精华榜 / 群发言榜图片。 ✨_

<a href="./LICENSE"><img src="https://img.shields.io/github/license/MortisBot/nonebot-plugin-group-rank.svg" alt="license"></a>
<a href="https://pypi.python.org/pypi/nonebot-plugin-group-rank"><img src="https://img.shields.io/pypi/v/nonebot-plugin-group-rank.svg" alt="pypi"></a>
<img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="python">

## 安装

在 NoneBot2 项目根目录下执行：

```bash
nb plugin install nonebot-plugin-group-rank
```

或手动安装：

```bash
pip install nonebot-plugin-group-rank
```

并在 `pyproject.toml` 的 `[tool.nonebot]` 中追加：

```toml
plugins = ["nonebot_plugin_group_rank"]
```

## 配置

在 `.env` 中配置（环境变量名即配置项大写）：

| 配置项 | 必填 | 默认值 | 说明 |
|:---:|:---:|:---:|:---|
| `GROUP_RANK_ENABLED` | 是 | `false` | 总开关 |
| `GROUP_RANK_ESSENCE_GROUPS` | 否 | 空 | 精华榜群白名单 |
| `GROUP_RANK_SPEAK_GROUPS` | 否 | 空 | 发言榜群白名单 |
| `GROUP_RANK_TOP_N` | 否 | `10` | 榜单人数 |
| `GROUP_RANK_WINDOW_SECONDS` | 否 | `86400` | 发言榜统计窗口 |
| `GROUP_RANK_BACKFILL_COUNT` | 否 | `1000` | 发言榜首次回填条数 |
| `GROUP_RANK_DB_PATH` | 否 | `data/group_rank/group_rank.db` | SQLite 路径 |
| `GROUP_RANK_BACKGROUND` | 否 | 无 | 自定义底图；不填为纯色渐变 |
| `GROUP_RANK_FONT_DIR` | 否 | 系统字体 | 字体目录（SourceHanSans OFL） |

## 使用

| 命令 | 权限 | 需要 @ | 说明 |
|:---:|:---:|:---:|:---|
| `精华榜` | 群员 | 是 | 当前在库精华，按发送者计数 |
| `精华榜 7` | 群员 | 是 | 近 7×24 小时被设为精华的 |
| `发言榜` | 群员 | 是 | 统计窗口内发言次数 Top N |

需先在对应 `*_GROUPS` 中配置群号。

## 适配器

OneBot v11（`supported_adapters={"~onebot.v11"}`）。

## License

[MIT](./LICENSE)

> 维护模式：原项目已停止运营，本插件按 best-effort 维护，无 SLA。
