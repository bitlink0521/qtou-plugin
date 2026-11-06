---
name: qtou-connect
description: >-
  连接轻投（qtou）：登录与自动保存、多账号添加/切换/退出、鉴权规则、工具清单与通用返回/错误约定。
  用户说连轻投、装轻投、登录轻投、换轻投账号、退出轻投，或其他轻投技能需要先连上时用。
  未登录时第一步弹 RequestUserForm(kind=login, site=qtou.cn)，不要先无参数调用 qtou_account_add。
  表单密码只到 BrowserSecureFill，不要抄进 MCP 参数或聊天。
---
# 轻投：连接与账号

## 连接（新 bot 先看这一页）

未登录、本机没有账号、401、`AUTH_REQUIRED`，或用户说要登录：**第一步**由宿主弹出安全表单。不要先调用 `qtou_account_add`。

RequestUserForm：

- `kind`: `login`
- `site`: `qtou.cn`（域名。不是 IP，不是 `localhost` / `127.0.0.1`，不是 `agent.bitilinks.cn`）
- 字段：轻投用户名、轻投密码（掩码）

代签 POST（代理自己用，**不是**表单的 site）：`http://113.250.189.74:18081/api/v1/agent/auth/login`。`QTOU_LOGIN_URL` 只改代理的 POST 目标，不要把这个地址填进 `site`。

**平台限制：** RequestUserForm 的密码只进入 BrowserSecureFill，不会回到模型，也不能写成 MCP 参数。不要把表单密钥传给 `qtou_account_add`。不要在聊天里要明文密码。不要打开 bot 的 box 桌面代签。不要拷贝 `~/.qtou` 或 `qtpat_` key。这条链路补不上，停在这里并说明缺口。

`qtou_account_add` 的 inputSchema 始终有 `username` 和 `password`。GetDynamicTools 若把参数缓存成 `properties: {}`，那是旧缓存，不是「该无参数调用」。无参数调用会走 MCP elicitation；Grok Bot 不展示，调用以 `-32001` cancelled 结束。

收到 `-32001` 或 `error.data.code=AUTH_REQUIRED`：不要重试 elicitation。按 `data` 弹表：`action=RequestUserForm`，`kind=login`，`site=qtou.cn`，`loginUrl` 是上面的代签 POST，`fields` 是用户名和密码，`secretDelivery=BrowserSecureFill`。密钥仍然只到 BrowserSecureFill。

elicitation 只留给确实会弹出 MCP 表单的客户端（Codex 等），是可选回退，不是 Grok Bot 的第一步。不支持表单的本地客户端仍可用 macOS 对话框。答案只回给启动器，不进聊天。

1. 已连且 `agent_health` 通过则结束。
2. 否则立刻 RequestUserForm（见上）。不要先无参数调用 `qtou_account_add`。
3. 弹表之后不要把密码写入任何工具参数。登录若仍未完成，说明 BrowserSecureFill 缺口后停止。

## 多账号（插件启动器提供的本地工具）

- `qtou_account_list`：列出本机已登录的账号，标出当前账号。用户问「现在用的哪个账号」时调它。
- `qtou_account_add`：添加一个账号并切换为当前账号。Grok Bot 不要为了登录去调它。schema 里的 `username` / `password` 不能用来承接 RequestUserForm 的密钥。只有会展示 MCP elicitation 的客户端可以不传参数，由代理自己收凭据；取消或 `-32001` 时立刻改弹 RequestUserForm，不要再试 elicitation。
- `qtou_account_switch({ username })`：切换当前账号。
- `qtou_account_logout({ username? })`：退出账号（不传则退出当前账号），同时在服务端吊销它的 key。

切换或退出前，如果正在做入池确认、预警确认等多步操作，先提醒用户：待确认记录属于原账号，要切回去才能继续。不替用户决定切到哪个账号。

## MCP 与鉴权

| 项 | 值 |
| --- | --- |
| MCP URL | `http://113.250.189.74:18081/api/v1/agent/mcp`（可用环境变量 `QTOU_MCP_URL` 覆盖；默认即此地址。禁止写成 `agent.bitilinks.cn` 或 `localhost` / `127.0.0.1`） |
| 表单 site | `qtou.cn`（RequestUserForm 的 site。不是 IP，不是 localhost，不是 `agent.bitilinks.cn`） |
| 代签 POST（演示 74，写死） | `http://113.250.189.74:18081/api/v1/agent/auth/login`（可用 `QTOU_LOGIN_URL` 覆盖代理自己的 POST 目标。这不是表单 site） |
| 传输 | Streamable HTTP |
| 鉴权 | `Authorization: Bearer <agent_key>` |
| 连接器名 | `qtou`（Grok 上手工添加的可能叫 `轻投`，二者等价） |
| 插件变量 | `QTOU_CONNECTOR_TOKEN` |

签发：宿主先弹 RequestUserForm（`kind=login`，`site=qtou.cn`）。密码只进入 BrowserSecureFill，模型不能把它交给 `qtou_account_add` 或代 POST。支持 elicitation 的客户端由代理自己收凭据并代 POST `http://113.250.189.74:18081/api/v1/agent/auth/login`，得到窄 scope `agentKey` 后写入本机或 `QTOU_CONNECTOR_TOKEN`。审计不写密码明文；key 永不进聊天。

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

不手抄 PAT；不在聊天里要账号密码或 key；不把 RequestUserForm 的密码抄进 MCP 参数（密钥只到 BrowserSecureFill）；不拷贝他人 `~/.qtou`；不打开 bot 的 box 桌面代签页；不把表单 site 写成 IP、`agent.bitilinks.cn`（工场）或 `localhost` / `127.0.0.1`；不直连业务库；不与工场抢名；调工具不把参数对象、数组、数字写成字符串。
