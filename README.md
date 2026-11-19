# nonebot-plugin-group-rank

> 同系列插件与部署/架构文档：[`MortisBot/qqbot-plugins`](https://github.com/MortisBot/qqbot-plugins)（索引与文档仓）

QQ 群 **精华榜 / 发言榜** 图片插件（NoneBot2 + OneBot v11）。两个榜单共用一套数据模型、
渲染与头像缓存，只保留必要的差异：

- **精华榜**：调用 NapCat 的 `get_essence_msg_list` 实时拉取当前在库精华，按「被设为精华」
  的发送者计数；不落库、不回填历史。
- **发言榜**：只记录消息元数据（群号 / 用户 / 消息 id / 时间戳）到本地 SQLite；新群第一次
  出榜时用 `get_group_msg_history` 回填最近消息（上限 1000 条），自动跳过 bot 自己与 QQ
  官方机器人。

## 安装

```bash
nb plugin install nonebot-plugin-group-rank
```

或在源码目录里开发安装：

```bash
uv venv .venv --python 3.13
uv pip install -e ".[dev]"
```

需要 OneBot v11 实现（NapCat / LLOneBot 等）提供 `get_essence_msg_list`、
`get_group_msg_history`、`get_group_member_list`、`get_group_member_info`、
`get_group_info` 这些 API。

## 配置

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `GROUP_RANK_ENABLED` | `0` | 总开关；默认关闭，需显式开启 |
| `GROUP_RANK_ESSENCE_GROUPS` | 空 | 允许精华榜的群，逗号/空格分隔；空 = 不响应 |
| `GROUP_RANK_SPEAK_GROUPS` | 空 | 允许发言榜（含记录）的群；空 = 不响应 |
| `GROUP_RANK_TOP_N` | `10` | 榜单条数，1–50 |
| `GROUP_RANK_WINDOW_SECONDS` | `86400` | 发言榜窗口，3600–604800 |
| `GROUP_RANK_BACKFILL_COUNT` | `1000` | 首次回填拉取条数，0–1000 |
| `GROUP_RANK_DB_PATH` | `data/group_rank/group_rank.db` | 发言榜 SQLite 路径（相对路径按工作目录解析） |
| `GROUP_RANK_AVATAR_CACHE_DIR` | `data/group_rank/avatars` | 头像文件缓存目录 |
| `GROUP_RANK_AVATAR_TTL_DAYS` | `7` | 头像缓存有效期（天），0 = 不过期 |
| `GROUP_RANK_AVATAR_MAX_FILES` | `500` | 头像缓存文件数上限 |
| `GROUP_RANK_COOLDOWN_SECONDS` | `10` | 同一群同一用户的命令冷却 |
| `GROUP_RANK_BACKGROUND` | 空 | 可选背景图路径；空或读取失败时用渐变底 |
| `GROUP_RANK_FONT_DIR` | 空 | 可选字体目录（见下） |

示例：

```bash
GROUP_RANK_ENABLED=1
GROUP_RANK_ESSENCE_GROUPS=<群号>
GROUP_RANK_SPEAK_GROUPS=<群号>,<群号>
GROUP_RANK_TOP_N=10
GROUP_RANK_WINDOW_SECONDS=86400
```

## 命令

| 命令 | 作用 |
|---|---|
| `@bot 精华榜` | 当前在库的全部精华用户榜 |
| `@bot 精华榜 7` | 近 7×24 小时被设为精华的用户榜 |
| `@bot 发言榜` | 配置窗口内的发言次数榜 |

两条命令都要求**显式 @bot**，且群必须在对应白名单里；同一群同一用户受
`GROUP_RANK_COOLDOWN_SECONDS` 限制。输出为 1024×1536 PNG。

## 字体与背景

字体和背景图**不随包分发**（Source Han Sans 为 SIL OFL 授权，体积也大）。默认按
`GROUP_RANK_FONT_DIR` → 系统 DejaVu 的顺序查找；都没有时退回 Pillow 内置字体，
仍可出图（中文可能显示为方框）。

想得到设计稿效果：把 `SourceHanSansSC-{Heavy,Bold,Medium,Regular}.otf` 放到一个
目录，设置 `GROUP_RANK_FONT_DIR=<字体目录>`；背景图同理设置 `GROUP_RANK_BACKGROUND`。
缺文件只记一条 warning，不会导致插件加载失败。

## 数据与隐私

- 精华榜：只读 NapCat 当前数据，不落库。
- 发言榜：SQLite 只存 `group_id / user_id / message_id / ts` 四列，**不存消息内容**；
  超过窗口 1 小时的旧行会在计数时定期清理。
- 头像：按 `QQ 号 + 群号` 缓存在本地文件，按 TTL 与文件数上限自动清理。
- 群名、群成员信息（含 `is_robot`）有短 TTL 内存缓存。

## 维护模式

- 一键停用：`GROUP_RANK_ENABLED=0`（默认值），插件不响应命令、不记录消息、不建库。
- 只关某个榜：清空 `GROUP_RANK_ESSENCE_GROUPS` 或 `GROUP_RANK_SPEAK_GROUPS`。
- 重置发言榜：停服后删除 `GROUP_RANK_DB_PATH` 指向的 `.db`（含 `-wal` / `-shm`），
  下次启动会重建表；回填 marker 一并清空，会重新回填一次。
- 头像占空间：调小 `GROUP_RANK_AVATAR_MAX_FILES` / `GROUP_RANK_AVATAR_TTL_DAYS`，
  或直接删除缓存目录。

## 测试

```bash
uv venv .venv --python 3.13
uv pip install -e ".[dev]"
uv run pytest -q
```

测试不连 NapCat、不发消息：NapCat 调用全部用假 Bot 替换，渲染用系统 DejaVu 字体 +
渐变背景，覆盖 1 / 3 / 10 行出图。

## License

MIT
