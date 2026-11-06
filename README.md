# 轻投插件

连接轻投（qtou）投资管理系统，让 AI 帮你做三件事：

- **BP 入池**：发 BP → 出确认卡 → 确认后入池，并自动补全工商、团队、融资等字段
- **尽调报告**：按项目名或文档名检索轻投里的资料（扫描件按页看图读），写尽调报告初稿
- **投后风险预警**：巡检投后项目的财务、舆情与公告，按阈值分级，员工逐条确认后回写

插件 = **MCP（轻投工具）+ 技能（使用规则）**。只接 MCP 也能调工具，但没有技能时 AI 不知道「入池先出确认卡」「预警必须带出处」这些规矩，所以两样都要装。

默认连接演示环境 `http://113.250.189.74:18081/api/v1/agent/mcp`。

## 登录

新 bot 未登录、没有账号、401、`AUTH_REQUIRED`，或用户说要登录时：**第一步**弹出 RequestUserForm。

- `kind`: `login`
- `site`: `qtou.cn`（不是 IP，不是 `localhost` / `127.0.0.1`，不是 `agent.bitilinks.cn`）
- 字段：轻投用户名、轻投密码（掩码）

代签 POST（代理自己用，**不是**表单 site）：`http://113.250.189.74:18081/api/v1/agent/auth/login`。`QTOU_LOGIN_URL` 只覆盖这个 POST。MCP 默认地址是 `http://113.250.189.74:18081/api/v1/agent/mcp`，可用 `QTOU_MCP_URL` 覆盖。两个地址都不要写成工场或 localhost，也不要填进表单 site。

不要先无参数调用 `qtou_account_add`。那会走 MCP elicitation；Grok Bot 不展示，返回 `-32001` cancelled。`qtou_account_add` 的 schema 始终有 `username` 和 `password`。工具列表若被缓存成 `properties: {}`，仍不要无参数调用。

**平台限制：** RequestUserForm 的密码只进入 BrowserSecureFill，不会回到模型，也不能写入 `qtou_account_add` 或其他 MCP 参数。不要为此在聊天里要明文密码，不要打开 bot 的 box 桌面代签，不要拷贝 `~/.qtou` 或 `qtpat_…` key。插件补不上这条链路；弹表后登录仍未完成，就说明缺口并停止。

收到 `-32001` 或 `AUTH_REQUIRED`：不要重试 elicitation。`error.data` 含 `action=RequestUserForm`、`kind=login`、`site=qtou.cn`、`loginUrl`（代签 POST）、`fields`、`secretDelivery=BrowserSecureFill`。按此再弹同一张表。

**Codex 等会展示 elicitation 的客户端**：无参数 `qtou_account_add` 仍可由启动器自己收凭据（不进聊天）；不支持表单时弹 macOS 对话框。这是可选回退，不是 Grok Bot 的第一步。登录成功后由插件写入本机 `~/.qtou/`。

支持多个账号，直接对 AI 说：「添加轻投账号」「切换到 xx 账号」「现在用的哪个轻投账号」「退出 xx 账号」。

需要本机 `python3` **≥ 3.7**（`tools/qtou_mcp_proxy.py` 使用了 `subprocess.run(..., capture_output=True, text=True)`，二者均为 3.7 引入；语法用 `ast.parse(..., feature_version=(3,7))` 可通过。Mac 若提示缺命令，按系统提示装开发者工具即可）。

入池时天眼查查不到公司，会由当前使用插件的 AI 联网搜公开资料（有 Tavily 用 Tavily，没有就用它自带的搜索并打开网页取正文）、自己核实后建档，不用另配 Grok。无人值守脚本要用 Tavily key 或 Grok API 时，分别放到 `~/.qtou/tavily-key`、`~/.qtou/grok-credentials`（权限设成 600），插件自动读取，不用在聊天里提供。

## 安装

### Codex

```bash
codex plugin marketplace add bitlink0521/qtou-plugin
codex plugin add qtou@qtou-plugin
```

更新：`codex plugin marketplace upgrade qtou-plugin`

### Grok Bot

前置：本机 `python3` ≥ 3.7（同上）。

在 **Connect Apps / 插件市场** 搜索并安装 **qtou**（市场条目 id `85237826`；也可让 bot 执行安装）。

装好后连接器走本机 `tools/qtou_mcp_proxy.py`（stdio）。首次使用时宿主先弹 RequestUserForm（`kind=login`，`site=qtou.cn`），不要先无参数调用 `qtou_account_add`，不要依赖 MCP elicitation。表单密码只到 BrowserSecureFill，不要抄进工具参数、聊天或 `qtpat_…`，不要拷贝 `~/.qtou`，不要打开 bot 的 box 桌面代签。代签 POST 见上文，写死为演示站 74，且不是表单 site。

手动配 HTTP 的可继续用根目录 `mcp.json`（Bearer `${QTOU_CONNECTOR_TOKEN}`）。

市场入口备忘（不确定桌面端具体菜单名时，把下面链接发给 bot 或浏览器打开）：
`https://cursor.com/grok-bot/link/v1/marketplace?tab=plugins`

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
  - `qtou-bp-intake`（轻投：BP 入池）：10 步执行清单与完成标准（含 `FIELDS.md` 字段对照、`VISUALS.md` 图片、`ENRICHMENT.md` 公开信息补全）
  - `qtou-dd-report`（轻投：尽调报告）：检索文档、扫描件看图读、写初稿（含 `DD-REPORT-WRITING.md`）
  - `qtou-risk-alert`（轻投：投后风险预警）：分级、出处、确认后回写
- **MCP**：服务端的轻投工具，加上 4 个账号工具（`qtou_account_list / add / switch / logout`）。Codex / Grok Bot 市场 / WorkBuddy 经 `tools/qtou_mcp_proxy.py`（登录与多账号）；Cursor 仍用根目录 `mcp.json` HTTP 直连（需 `QTOU_CONNECTOR_TOKEN`）。
- **辅助脚本**：`tools/project-enrichment`（字段补全）、`tools/risk-patrol`（自动巡检）
- **Logo**：`assets/logo.png`

## 维护

- 名称、版本、描述、logo、MCP 地址只改 `plugin-meta.json`，然后运行 `python3 scripts/build_manifests.py` 生成各客户端的清单（Codex、Cursor、Claude/WorkBuddy、Grok）和 MCP 配置；`tools/test_manifests.py` 会检查是否同步。
- 工具脚本共用 `tools/qtou_shared.py`（HTTP、Tavily、Grok、本机账号存储），新脚本不要再各写一份。
- 测试：在 `tools`、`tools/risk-patrol`、`tools/project-enrichment` 下分别运行 `python3 -m unittest`。
