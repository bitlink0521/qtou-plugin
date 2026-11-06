# 轻投插件

连接轻投（qtou）投资管理系统，让 AI 帮你做三件事：

- **BP 入池**：发 BP → 出确认卡 → 确认后入池，并自动补全工商、团队、融资等字段
- **尽调报告**：按项目名或文档名检索轻投里的资料（扫描件按页看图读），写尽调报告初稿
- **投后风险预警**：巡检投后项目的财务、舆情与公告，按阈值分级，员工逐条确认后回写

插件 = **MCP（轻投工具）+ 技能（使用规则）**。只接 MCP 也能调工具，但没有技能时 AI 不知道「入池先出确认卡」「预警必须带出处」这些规矩，所以两样都要装。

默认连接演示环境 `http://113.250.189.74:18081/api/v1/agent/mcp`。

## 登录

第一次使用时会请你登录轻投（Codex 弹出对话内表单；不支持表单的客户端弹 macOS 对话框），登录后保存在本机 `~/.qtou/`，以后直接用，失效会再请你登录一次。账号密码只交给插件，不进聊天，也不要把 `qtpat_…` 贴到聊天里。

支持多个账号，直接对 AI 说：「添加轻投账号」「切换到 xx 账号」「现在用的哪个轻投账号」「退出 xx 账号」。

需要本机有 `python3`（Mac 第一次用时按提示安装开发者工具即可）。

入池时天眼查查不到公司，会由当前使用插件的 AI 联网搜公开资料（有 Tavily 用 Tavily，没有就用它自带的搜索并打开网页取正文）、自己核实后建档，不用另配 Grok。无人值守脚本要用 Tavily key 或 Grok API 时，分别放到 `~/.qtou/tavily-key`、`~/.qtou/grok-credentials`（权限设成 600），插件自动读取，不用在聊天里提供。

## 安装

### Codex

```bash
codex plugin marketplace add bitlink0521/qtou-plugin
codex plugin add qtou@qtou-plugin
```

更新：`codex plugin marketplace upgrade qtou-plugin`

### Grok Bot（桌面客户端）

插件 → **Add custom plugin** → 填 `https://github.com/bitlink0521/qtou-plugin`。装好后新开会话即可。

### WorkBuddy

WorkBuddy 不按插件装，分别接 MCP 和技能：

1. 先把本仓库克隆到本机，例如 `~/qtou-plugin`：`git clone https://github.com/bitlink0521/qtou-plugin.git ~/qtou-plugin`
2. **MCP**：连接器 → 自定义连接器，在 `mcp.json` 里加（把路径换成你的用户名）：
   ```json
   {
     "mcpServers": {
       "qtou": {
         "command": "python3",
         "args": ["/Users/<你的用户名>/qtou-plugin/tools/qtou_mcp_proxy.py"],
         "timeout": 600000
       }
     }
   }
   ```
3. **技能**：把 4 个技能链接到 WorkBuddy 的技能目录：
   ```bash
   for s in ~/qtou-plugin/skills/*; do ln -s "$s" ~/.workbuddy-ai/skills/; done
   ```

更新：在 `~/qtou-plugin` 里 `git pull`。

### Grok 命令行

```bash
grok plugin install https://github.com/bitlink0521/qtou-plugin --trust
```

更新：`grok plugin update`

## 包含

- **技能（4 个）**
  - `qtou-connect`（轻投：连接与账号）：登录、多账号、工具清单与通用规则
  - `qtou-bp-intake`（轻投：BP 入池）：确认卡、入池后自动补全（含 `PROJECT-ENRICHMENT.md`、`BP-VISUALS.md`）
  - `qtou-dd-report`（轻投：尽调报告）：检索文档、扫描件看图读、写初稿（含 `DD-REPORT-WRITING.md`）
  - `qtou-risk-alert`（轻投：投后风险预警）：分级、出处、确认后回写
- **MCP**：服务端的轻投工具，加上 4 个账号工具（`qtou_account_list / add / switch / logout`）。Codex、Grok、WorkBuddy 都经 `tools/qtou_mcp_proxy.py` 连接（负责登录和多账号）；Cursor 用 `mcp.json` 直连。
- **辅助脚本**：`tools/project-enrichment`（字段补全）、`tools/risk-patrol`（自动巡检）
- **Logo**：`assets/logo.png`

## 维护

- 名称、版本、描述、logo、MCP 地址只改 `plugin-meta.json`，然后运行 `python3 scripts/build_manifests.py` 生成各客户端的清单（Codex、Cursor、Claude/WorkBuddy、Grok）和 MCP 配置；`tools/test_manifests.py` 会检查是否同步。
- 工具脚本共用 `tools/qtou_shared.py`（HTTP、Tavily、Grok、本机账号存储），新脚本不要再各写一份。
- 测试：在 `tools`、`tools/risk-patrol`、`tools/project-enrichment` 下分别运行 `python3 -m unittest`。
