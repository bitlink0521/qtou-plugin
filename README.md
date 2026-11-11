# 轻投插件

连接轻投（qtou）投资管理系统，让 AI 帮你做三件事：

- **BP 入池**：发 BP → 出确认卡 → 确认后入池，并自动补全工商、团队、融资等字段
- **尽调报告**：按项目名或文档名检索轻投里的资料（扫描件按页看图读），写尽调报告初稿
- **投后风险预警**：巡检投后项目的财务、舆情与公告，按阈值分级，员工逐条确认后回写

插件 = **MCP（轻投工具）+ 技能（使用规则）**。只接 MCP 也能调工具，但没有技能时 AI 不知道「入池先出确认卡」「预警必须带出处」这些规矩，所以两样都要装。

默认连接演示环境 `https://qtou.handsels.com/api/v1/agent/mcp`（演示环境在公司内网服务器上，经 Cloudflare Tunnel 提供 HTTPS 访问，网页系统是 https://qtou.handsels.com/qtou）。

## 登录

所有客户端都直连 `https://qtou.handsels.com/api/v1/agent/mcp`，**不用装 Python 或任何软件**，Windows 和 Mac 一样。第一次使用时客户端会弹出（或给出链接）轻投登录页，在浏览器里输入轻投账号密码即可，登录后页面自动关闭或提示回到客户端。

换账号：在客户端的 MCP / 连接器设置里退出 qtou 的登录，再用另一个账号登录。不要在聊天里发密码或 key。

入池时天眼查查不到公司，会由当前使用插件的 AI 联网搜公开资料、自己核实后建档，不用另配 Grok。

## 安装

### Codex

```bash
codex plugin marketplace add bitlink0521/qtou-plugin
codex plugin add qtou@qtou-plugin
```

更新：`codex plugin marketplace upgrade qtou-plugin`。第一次用会自动弹出登录页；没弹的话运行 `codex mcp login qtou`。

### Claude Code

```text
/plugin marketplace add bitlink0521/qtou-plugin
/plugin install qtou@qtou-plugin
```

装好后在对话里输入 `/mcp`，选 `qtou` 登录。更新：`/plugin marketplace update qtou-plugin`。

### WorkBuddy

WorkBuddy 不按插件装，分别接 MCP 和技能：

1. **MCP**：连接器 → 自定义连接器，在 `mcp.json` 里加：
   ```json
   {
     "mcpServers": {
       "qtou": {
         "type": "http",
         "url": "https://qtou.handsels.com/api/v1/agent/mcp",
         "timeout": 600000
       }
     }
   }
   ```
   保存后在连接器列表里点 qtou 登录。
2. **技能**：把仓库克隆到本机（如 `~/qtou-plugin`），把 4 个技能链接到 WorkBuddy 的技能目录：
   ```bash
   git clone https://github.com/bitlink0521/qtou-plugin.git ~/qtou-plugin
   for s in ~/qtou-plugin/skills/*; do ln -s "$s" ~/.workbuddy-ai/skills/; done
   ```

更新：在 `~/qtou-plugin` 里 `git pull`。

### Grok Bot

在 **Connect Apps / 插件市场** 搜索并安装 **qtou**（市场条目 id `85237826`；也可让 bot 执行安装），然后在连接器里点 qtou 登录。

市场入口备忘（不确定桌面端具体菜单名时，把下面链接发给 bot 或浏览器打开）：
`https://cursor.com/grok-bot/link/v1/marketplace?tab=plugins`

## 包含

- **技能（4 个）**
  - `qtou-connect`（轻投：连接与账号）：登录、多账号、工具清单与通用规则
  - `qtou-bp-intake`（轻投：BP 入池）：10 步执行清单与完成标准（含 `FIELDS.md` 字段对照、`VISUALS.md` 图片、`ENRICHMENT.md` 公开信息补全）
  - `qtou-dd-report`（轻投：尽调报告）：检索文档、扫描件看图读、写初稿（含 `DD-REPORT-WRITING.md`）
  - `qtou-risk-alert`（轻投：投后风险预警）：分级、出处、确认后回写
- **MCP**：服务端的轻投工具，所有客户端直连服务端、浏览器登录。`tools/qtou_mcp_proxy.py` 只留给无人值守的巡检脚本。
- **辅助脚本**：`tools/project-enrichment`（字段补全）、`tools/risk-patrol`（自动巡检）
- **Logo**：`assets/logo.png`

## 维护

- 名称、版本、描述、logo、MCP 地址只改 `plugin-meta.json`，然后运行 `python3 scripts/build_manifests.py` 生成各客户端的清单（Codex、Cursor、Claude/WorkBuddy、Grok）和 MCP 配置；`tools/test_manifests.py` 会检查是否同步。
- 工具脚本共用 `tools/qtou_shared.py`（HTTP、Tavily、Grok、本机账号存储），新脚本不要再各写一份。
- 测试：在 `tools`、`tools/risk-patrol`、`tools/project-enrichment` 下分别运行 `python3 -m unittest`。
