<div align="center">
  <a href="https://v2.nonebot.dev/store">
    <img src="https://raw.githubusercontent.com/fllesser/nonebot-plugin-template/refs/heads/resource/.docs/NoneBotPlugin.svg" width="310" alt="NoneBotPlugin">
  </a>

# nonebot-plugin-group-rank

_✨ 群精华榜 / 群发言榜图片 ✨_

[![LICENSE](https://img.shields.io/github/license/MortisBot/nonebot-plugin-group-rank.svg)](./LICENSE)
[![pypi](https://img.shields.io/pypi/v/nonebot-plugin-group-rank.svg)](https://pypi.python.org/pypi/nonebot-plugin-group-rank)
![python](https://img.shields.io/badge/python-3.10+-blue.svg)

</div>

## 📖 介绍

生成群 **精华榜** 与 **发言榜** 图片。两榜共用渲染与头像缓存，但数据来源不同：精华榜实时读 NapCat，发言榜用本地 SQLite 统计（只存消息元数据，不存内容）。

## 💿 安装

<details open>
<summary>使用 nb-cli 安装</summary>

在 NoneBot2 项目根目录下执行：

```bash
nb plugin install nonebot-plugin-group-rank --upgrade
```

国内网络可换镜像源：

```bash
nb plugin install nonebot-plugin-group-rank --upgrade -i "https://pypi.tuna.tsinghua.edu.cn/simple"
```

</details>

<details>
<summary>使用包管理器安装</summary>

在 NoneBot2 项目根目录下执行其一：

```bash
uv add nonebot-plugin-group-rank
# 或
pdm add nonebot-plugin-group-rank
# 或
poetry add nonebot-plugin-group-rank
```

直接装仓库主分支（PyPI 包发布前可用）：

```bash
uv add git+https://github.com/MortisBot/nonebot-plugin-group-rank@main
```

然后在 `pyproject.toml` 的 `[tool.nonebot]` 中追加：

```toml
plugins = ["nonebot_plugin_group_rank"]
```

</details>

## ⚙️ 配置

在 NoneBot2 项目的 `.env` 中配置（配置项即环境变量名，大写）：

| 配置项 | 必填 | 默认值 | 说明 |
|:---:|:---:|:---:|:---|
| `GROUP_RANK_ENABLED` | 是 | `false` | 总开关 |
| `GROUP_RANK_ESSENCE_GROUPS` | 否 | 空 | 精华榜群白名单 |
| `GROUP_RANK_SPEAK_GROUPS` | 否 | 空 | 发言榜群白名单 |
| `GROUP_RANK_TOP_N` | 否 | `10` | 榜单人数 |
| `GROUP_RANK_WINDOW_SECONDS` | 否 | `86400` | 发言榜统计窗口 |
| `GROUP_RANK_BACKFILL_COUNT` | 否 | `1000` | 发言榜首次回填条数 |
| `GROUP_RANK_DB_PATH` | 否 | `data/group_rank/group_rank.db` | SQLite 路径 |
| `GROUP_RANK_BACKGROUND` | 否 | 无 | 自定义底图，不填为纯色渐变 |
| `GROUP_RANK_FONT_DIR` | 否 | 系统字体 | 字体目录（SourceHanSans，OFL） |

## 🎉 使用

| 命令 | 权限 | 需要 @ | 范围 | 说明 |
|:---:|:---:|:---:|:---:|:---|
| `精华榜` | 群员 | 是 | 群聊 | 当前在库精华，按发送者计数 |
| `精华榜 7` | 群员 | 是 | 群聊 | 近 7×24 小时被设为精华的 |
| `发言榜` | 群员 | 是 | 群聊 | 统计窗口内发言次数 Top N |

## 🔌 适配器

OneBot v11（`supported_adapters={"~onebot.v11"}`）。精华榜依赖 NapCat 的 `get_essence_msg_list`；发言榜首次命令会回填最近最多 1000 条。

## 📄 License

[MIT](./LICENSE) · 维护模式（best-effort，无 SLA）
