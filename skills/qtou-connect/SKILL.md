---
name: qtou-connect
description: >-
  连接轻投（qtou）：登录与自动保存、多账号添加/切换/退出、鉴权规则、工具清单与通用返回/错误约定。
  用户说连轻投、装轻投、登录轻投、换轻投账号、退出轻投，或其他轻投技能需要先连上时用。
---
# 轻投：连接与账号

## 连接

**默认登录（宿主 bot，如 Grok Bot）**：未登录 / 401 / 第一次安装，**直接**在用户自己的聊天里弹出安全表单（RequestUserForm / Vault），收取轻投用户名 + 掩码密码。不要先赌、也不要依赖 MCP elicitation。elicitation 若被取消、报 `-32001`，或用户说「没看到 / 看不到表单」，立刻改弹同一张安全表单。插件自己调用不了 RequestUserForm，未登录时会返回 JSON-RPC `-32001`，`error.data` 为 `AUTH_REQUIRED`（含代签地址和字段），宿主应按此弹表，不要叫用户再试一次 elicitation。

1. 已连且冒烟（`agent_health`）通则结束。
2. 未登录：弹 RequestUserForm（字段：轻投用户名、轻投密码（掩码））。站点必须写死为代签登录 URL `http://113.250.189.74:18081/api/v1/agent/auth/login`（轻投演示站 74）。禁止写成 `agent.bitilinks.cn`（工场，不是轻投）或 `localhost` / `127.0.0.1`（安全表单会拒）。
3. 拿到表单结果后：调用 `qtou_account_add({ username, password })`（stdio 代理代签并写入本机 `~/.qtou/`，不要回显密码）；若连接器是 HTTP，也可由宿主把表单结果 POST 到上述代签地址，将返回的 `agentKey` 写入插件变量 `QTOU_CONNECTOR_TOKEN`（key 永不进聊天）。然后 `agent_health` 冒烟。
4. Codex / WorkBuddy / Grok 命令行补充路径：插件的 `qtou` 连接由 `tools/qtou_mcp_proxy.py` 启动。没有可用账号或 key 失效时，它仍可请客户端弹出 MCP 表单（不支持表单的客户端改用 macOS 对话框），签发后保存在本机 `~/.qtou/`，之后自动复用。表单内容只回给启动器，不进聊天。这不是 Grok Bot 的默认路径。工具返回「未登录轻投：已取消登录」时，告诉用户再发一次请求、在表单里登录。

## 多账号（插件启动器提供的本地工具）

- `qtou_account_list`：列出本机已登录的账号，标出当前账号。用户问「现在用的哪个账号」时调它。
- `qtou_account_add`：添加一个账号并切换为当前账号。优先传入 RequestUserForm 收回的 `username` 与 `password`；不传参数时，支持 elicitation 的客户端会弹 MCP 表单（取消或看不到则返回 `AUTH_REQUIRED`，宿主应立刻改弹 RequestUserForm）。
- `qtou_account_switch({ username })`：切换当前账号。
- `qtou_account_logout({ username? })`：退出账号（不传则退出当前账号），同时在服务端吊销它的 key。

切换或退出前，如果正在做入池确认、预警确认等多步操作，先提醒用户：待确认记录属于原账号，要切回去才能继续。不替用户决定切到哪个账号。

## MCP 与鉴权

| 项 | 值 |
| --- | --- |
| MCP URL | `http://113.250.189.74:18081/api/v1/agent/mcp`（可用环境变量 `QTOU_MCP_URL` 覆盖；默认即此地址。禁止写成 `agent.bitilinks.cn` 或 `localhost` / `127.0.0.1`） |
| 代签登录 URL（演示 74，写死） | `http://113.250.189.74:18081/api/v1/agent/auth/login`（可用 `QTOU_LOGIN_URL` 覆盖代理自己的 POST 目标；宿主弹表时必须用这个演示站地址，禁止写成工场或 localhost） |
| 传输 | Streamable HTTP |
| 鉴权 | `Authorization: Bearer <agent_key>` |
| 连接器名 | `qtou`（Grok 上手工添加的可能叫 `轻投`，二者等价） |
| 插件变量 | `QTOU_CONNECTOR_TOKEN` |

签发：弹用户聊天里的安全表单收账密（RequestUserForm，不收 PAT，不在聊天里要明文密码）→ 调用 `qtou_account_add` 或代调 `POST http://113.250.189.74:18081/api/v1/agent/auth/login` → 得窄 scope `agentKey` → 由插件写入本机或写入 `QTOU_CONNECTOR_TOKEN`。审计不写密码明文；key 永不进聊天。

## 只走 MCP 工具（强制）

业务操作只能调已连接的 qtou 工具：不自己读取 key，不用 curl / 脚本 / fetch 调 `/api/v1/agent/**`，不直连数据库，不读服务器本地文件。连不上或缺工具时如实报错并停止；客户端缓存了旧工具列表时先重连再查。唯一例外是 `agent_projects_bp_upload_url` 返回的一次性上传地址（见 `qtou-bp-intake`）。

## 工具

| 场景 | 工具 |
|---|---|
| 通用 | `agent_health` · `agent_dicts` |
| BP 入池 | `agent_bp_parse` · `agent_projects_create_pending` · `agent_projects_get` · `agent_projects_company_choose` · `agent_projects_confirm` · `agent_projects_reject` · `agent_projects_user_fields` · `agent_projects_bp_schema` · `agent_projects_bp_get` · `agent_projects_bp_source` · `agent_projects_bp_fill` · `agent_projects_bp_upload_url` · `agent_projects_bp_attach` · `agent_projects_bp_pages` · `agent_projects_bp_assets` · `agent_projects_profile_get` · `agent_projects_profile_fill` |
| 尽调报告 | `agent_documents_search` · `agent_documents_content` · `agent_documents_pages` |
| 投后预警 | `agent_portfolio_list` · `agent_portfolio_quarterly` · `agent_risk_threshold_get` · `agent_risk_alerts_list` · `agent_risk_alerts_create` |

写操作都要用户确认：入池要过确认卡（见 `qtou-bp-intake`），预警逐条确认（见 `qtou-risk-alert`）。用户确认入池后的补空值写入按 `qtou-bp-intake` 自动执行，不再逐项确认。

## 返回与错误

- 列表类工具（`agent_documents_search`、`agent_portfolio_list`、`agent_risk_alerts_list`、`agent_dicts`）返回 `{ items: [...] }`。`agent_portfolio_list`、`agent_risk_alerts_list`、`agent_documents_search` 分页：传 `page`（从 1 起）和 `pageSize`（1–50，默认 20），返回 `total`、`hasMore`；要全量时 `hasMore: true` 就继续翻。
- 失败返回 `isError: true`，正文 `{"error": {"code", "message", "tool"}}`。code 有 `INVALID_ARGUMENT`、`NOT_FOUND`、`FAILED_PRECONDITION`、`BACKEND_DB_ERROR`、`INTERNAL_ERROR`、`UPSTREAM_*`。把 code 和 message 如实告诉用户，带 `ref=…` 的一并给出（管理员凭它查日志）；不改走别的路径，也不写成「没找到」。
- 参数传 JSON 对象：对象传对象、数组传数组、数字传数字、`confirmed` 传布尔。`arguments` 被序列化成字符串会返回「参数 arguments 格式不对，应为对象」，改成对象重发即可。

## 不做

不手抄 PAT；不在聊天里要账号密码或 key；不拷贝他人 `~/.qtou`；不打开 bot 的 box 桌面代签页；不把登录站点写成 `agent.bitilinks.cn`（工场）或 `localhost` / `127.0.0.1`；不直连业务库；不与工场抢名；调工具不把参数对象、数组、数字写成字符串。
