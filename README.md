# nonebot-plugin-group-rank

> 群 **精华榜** / **发言榜** 图片插件。两个榜共用一套渲染与头像缓存，但数据来源不同：
> 精华榜实时读 NapCat，发言榜用本地 SQLite 统计（只存消息元数据，不存内容）。

## 命令一览

| 命令 | 需要 @ | 说明 |
|:---:|:---:|:---|
| `精华榜` | 是 | 当前在库的全部精华，按发送者计数 |
| `精华榜 7` | 是 | 近 7×24 小时内被设为精华的 |
| `发言榜` | 是 | 统计窗口内发言次数 Top N |

命令只对 `GROUP_RANK_ESSENCE_GROUPS` / `GROUP_RANK_SPEAK_GROUPS` 里配置的群生效。

## 安装

```bash
nb plugin install nonebot-plugin-group-rank
```

手动：`pip install nonebot-plugin-group-rank`，并在 `pyproject.toml` 加：

```toml
[tool.nonebot]
plugins = ["nonebot_plugin_group_rank"]
```

## 配置

```dotenv
GROUP_RANK_ENABLED=true
GROUP_RANK_ESSENCE_GROUPS=123456789
GROUP_RANK_SPEAK_GROUPS=123456789
GROUP_RANK_TOP_N=10
GROUP_RANK_WINDOW_SECONDS=86400
GROUP_RANK_BACKFILL_COUNT=1000
# 可选：自定义底图/字体
# GROUP_RANK_BACKGROUND=./assets/rank_bg.jpg
# GROUP_RANK_FONT_DIR=./assets/fonts
```

| 变量 | 默认 | 说明 |
|:---:|:---:|:---|
| `GROUP_RANK_ENABLED` | `false` | 总开关 |
| `GROUP_RANK_TOP_N` | `10` | 榜单人数 |
| `GROUP_RANK_WINDOW_SECONDS` | `86400` | 发言榜窗口 |
| `GROUP_RANK_BACKFILL_COUNT` | `1000` | 首次命令回填条数上限 |
| `GROUP_RANK_DB_PATH` | `data/group_rank/group_rank.db` | SQLite 路径 |

## 依赖与边界

- OneBot v11；精华榜依赖 NapCat 的 `get_essence_msg_list`，换实现会退化
- 无底图时回退纯色渐变；字体建议使用 SourceHanSans（OFL）
- 发言榜首次命令会回填最近最多 1000 条，离线期间消息不补

## License

[MIT](./LICENSE)
