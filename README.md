# 轻投插件

连接轻投（qtou）投资管理系统，让 AI 帮你做三件事：

- **BP 入池**：发 BP → 出确认卡 → 确认后入池，并自动补全工商、团队、融资等字段
- **尽调报告**：按项目名或文档名检索轻投里的资料（扫描件按页看图读），写尽调报告初稿
- **投后风险预警**：巡检投后项目的财务、舆情与公告，按阈值分级，员工逐条确认后回写

插件 = **MCP（轻投工具）+ 技能（使用规则）**。只接 MCP 也能调工具，但没有技能时 AI 不知道「入池先出确认卡」「预警必须带出处」这些规矩，所以两样都要装。

默认连接内网演示环境 `http://192.168.110.142:18081/api/v1/agent/mcp`（2026-11-09 起从公网 74 迁到公司内网）。只有能访问公司内网的客户端能连，云端运行的 Grok Bot 等连不上。

## 登录

默认代签登录地址（轻投内网演示环境 142，写死）：`http://192.168.110.142:18081/api/v1/agent/auth/login`。可用环境变量 `QTOU_LOGIN_URL` 覆盖，但**禁止**写成 `agent.bitilinks.cn`（那是工场，不是轻投）、`localhost` 或 `127.0.0.1`（安全表单会拒绝）。MCP 默认地址是 `http://192.168.110.142:18081/api/v1/agent/mcp`，可用 `QTOU_MCP_URL` 覆盖，同样不要写成工场或 localhost。

**Grok Bot 等宿主 bot（默认路径）**：未登录 / 401 / 第一次安装时，由宿主发起安全登录采集轻投用户名与密码。不要先调空的 `qtou_account_add` 去赌 MCP elicitation；若 elicitation 被取消、报 `-32001`，或用户看不到表单，立刻改由宿主安全登录。插件自己弹不出宿主的安全采集控件；未登录时可能返回 JSON-RPC `-32001`，`error.data` 为 `AUTH_REQUIRED`（`action=HostSecureLogin`，含 `secretRequest=QTOU_LOGIN_PASSWORD`），宿主应按此处理。仅弹出网页类安全表单并不等于密码已交给插件；RequestUserForm 可与 secret-request 并存，但不能代替交密。

首登流程：先由**当前这个 bot** 发聊天里的 `secret-request` 掩码框，把密码写入环境变量 `QTOU_LOGIN_PASSWORD`（可选同时写入 `QTOU_LOGIN_USERNAME`）。每个 bot 必须用自己发的 secret-request，不能沿用其他 bot 的变量。填写后若 stdio 代理早已启动，需要重装/重连该 MCP，代理才能读到新变量。然后再调用 `qtou_account_add`（可不传 `password`；若同时传了参数，参数优先）。代理按 参数 > 环境变量 > elicitation 取凭据，三者都没有则返回 `AUTH_REQUIRED` 并提示使用 secret-request。stdio 代理会 POST 到写死的代签地址并写入本机，**不**用工具参数覆盖站点和 URL，登录成功后也不清除环境变量；密码不进日志、报错和返回值。若连接器是 HTTP，也可由宿主把账密 POST 到上述代签地址，将返回的 `agentKey` 写入插件变量 `QTOU_CONNECTOR_TOKEN`（key 永不进聊天）。然后调用 `agent_health` 冒烟。

**Codex**：没有可用账号、没有传入参数、也没有上述环境变量时，启动器仍可通过对话内 MCP 表单（elicitation）登录；不支持表单的客户端弹 macOS 对话框。这是补充路径，不是宿主 bot 的默认路径。

登录后由插件自己写入本机 `~/.qtou/`，以后直接用，失效会再请你登录。

禁止：在聊天里索要明文密码或 `qtpat_…` key；拷贝他人的 `~/.qtou` 或 key 文件；打开 bot 的 box 桌面去完成代签；把登录站点写成 `agent.bitilinks.cn`、`localhost` 或 `127.0.0.1`。

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

装好后连接器走本机 `tools/qtou_mcp_proxy.py`（stdio）：首次使用时由宿主 bot 先发 secret-request（变量名 `QTOU_LOGIN_PASSWORD`，每个 bot 自己发；可与 RequestUserForm 并存），再调用 `qtou_account_add` 写入本机 `~/.qtou/`；不要赌 MCP elicitation，不要手填 `qtpat_…`，不要拷贝 `~/.qtou`，不要打开 bot 的 box 桌面代签。代签地址见上文，写死为内网演示环境 142，不允许用参数覆盖。

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
