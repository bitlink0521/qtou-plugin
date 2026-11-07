---
name: qtou-connect
description: >-
  连接轻投（qtou）：登录与自动保存、多账号添加/切换/退出、鉴权规则、工具清单与通用返回/错误约定。
  用户说连轻投、装轻投、登录轻投、换轻投账号、退出轻投，或其他轻投技能需要先连上时用。
---
# 轻投：连接与账号

## 连接

**默认登录（宿主 bot）**：没有已保存的 key，或业务调用返回 `-32001` / `AUTH_REQUIRED` 时，由宿主采集轻投用户名与密码，再调用 `qtou_account_add`。未登录时不要向业务接口发请求。已经登录后，服务端 HTTP 500、401、403 或 JSON-RPC error 是失败：原样告诉用户，不要包装成成功，也不要因此自动登录。插件自己弹不出宿主的安全采集控件。`error.data` 为 `AUTH_REQUIRED` 时才表示需要登录（`action=HostSecureLogin`，`secretRequest=QTOU_LOGIN_PASSWORD`）。

注意：仅弹出网页类安全表单（例如只能把密文交给浏览器填充的 RequestUserForm）**不等于**已经把密码交给了本插件。RequestUserForm 可以和下面的 secret-request **并存**，但不能代替交密通路。密码不得进聊天、不得打印。若使用 RequestUserForm，`site` 必须是域名 `qtou.cn`（禁止 IP、`localhost`、`127.0.0.1`、`agent.bitilinks.cn`）；代签 POST 地址（演示站 74）**不是**表单 site，二者不要混用，也不允许用工具参数覆盖站点和 URL。

**首登流程（宿主 bot）**：

1. 已连且冒烟（`agent_health`）通则结束。
2. 未登录：宿主先发聊天里的 `secret-request` 掩码框，把密码写入环境变量 `QTOU_LOGIN_PASSWORD`（可选同时写入 `QTOU_LOGIN_USERNAME`，或用非密方式询问用户名）。**每个 bot 必须使用自己发起的 secret-request**，不能沿用其他 bot 写入的变量。secret-request 写入的是发起该请求的那个 bot 的 `process.env`；stdio 代理在启动时才能读到这些变量，所以填写后若代理是早就拉起的，需要重装/重连该 MCP 后再调用登录工具。
3. 再调用 `qtou_account_add`（可以只传 `username`，或不传 password）。代理取凭据的优先级是：工具参数 > 环境变量 `QTOU_LOGIN_PASSWORD` / `QTOU_LOGIN_USERNAME` > Codex elicitation。三者都没有则返回 `AUTH_REQUIRED`，并提示宿主用 secret-request（变量名 `QTOU_LOGIN_PASSWORD`）。
4. 代理把账密 POST 到写死的代签 URL `http://113.250.189.74:18081/api/v1/agent/auth/login`（站点和 URL 不允许覆盖），只把返回的 key 写入本机 `~/.qtou/`，不写密码。登录成功后**不清除**环境变量。密码不进日志、不进报错、不进返回值。若连接器是 HTTP，也可由宿主把账密 POST 到代签地址，将返回的 `agentKey` 写入插件变量 `QTOU_CONNECTOR_TOKEN`（key 永不进聊天）。然后 `agent_health` 冒烟。
5. 没有安全输入就停止。MCP elicitation 的密码字段只是普通 string，不能当作掩码。没有终端时也不要改用系统对话框。用户可以自己在终端执行 `python3 tools/qtou_mcp_proxy.py --login`（有可隐藏输入时才会问密码）。宿主则必须在代理进程启动前写入 `QTOU_LOGIN_PASSWORD`。若返回 `AUTH_REQUIRED` / `-32001`，不要循环空参 `qtou_account_add`，也不要让用户把密码打进聊天。

代签登录 URL（演示站 74，写死，供代理/宿主 POST）：`http://113.250.189.74:18081/api/v1/agent/auth/login`。禁止写成 `agent.bitilinks.cn` 或 `localhost` / `127.0.0.1`，也不允许用 `qtou_account_add` 的参数覆盖。

## 多账号（插件启动器提供的本地工具）

- `qtou_account_list`：列出本机已登录的账号，标出当前账号。用户问「现在用的哪个账号」时调它。
- `qtou_account_add`：添加一个账号并切换为当前账号。宿主应先 secret-request 写入 `QTOU_LOGIN_PASSWORD`（每个 bot 自己发），再调用本工具；也可以传入 `username` / `password`（参数优先于环境变量）。不要空参去赌 elicitation。三者都没有、取消或 `-32001` 时按 `AUTH_REQUIRED` 提示宿主发 secret-request。
- `qtou_account_switch({ username })`：切换当前账号。
- `qtou_account_logout({ username? })`：退出账号（不传则退出当前账号），同时在服务端吊销它的 key。

切换或退出前，如果正在做入池确认、预警确认等多步操作，先提醒用户：待确认记录属于原账号，要切回去才能继续。不替用户决定切到哪个账号。

## MCP 与鉴权

| 项 | 值 |
| --- | --- |
| MCP URL | `http://113.250.189.74:18081/api/v1/agent/mcp`（可用环境变量 `QTOU_MCP_URL` 覆盖；默认即此地址。禁止写成 `agent.bitilinks.cn` 或 `localhost` / `127.0.0.1`） |
| 代签登录 URL（演示 74，写死） | `http://113.250.189.74:18081/api/v1/agent/auth/login`（可用 `QTOU_LOGIN_URL` 覆盖代理自己的 POST 目标；禁止写成 `agent.bitilinks.cn` 或 `localhost` / `127.0.0.1`） |
| 传输 | Streamable HTTP |
| 鉴权 | `Authorization: Bearer <agent_key>` |
| 连接器名 | `qtou`（Grok 上手工添加的可能叫 `轻投`，二者等价） |
| 插件变量 | `QTOU_CONNECTOR_TOKEN` |

签发：宿主用 secret-request（可与 RequestUserForm 并存）采集账密（不收 PAT，不在聊天里要明文密码）→ 调用 `qtou_account_add`（读参数或环境变量 `QTOU_LOGIN_PASSWORD` / 可选 `QTOU_LOGIN_USERNAME`）或代调 `POST http://113.250.189.74:18081/api/v1/agent/auth/login` → 得窄 scope `agentKey` → 由插件写入本机或写入 `QTOU_CONNECTOR_TOKEN`。登录成功后不清除环境变量。审计不写密码明文；key 永不进聊天。

## 只走 MCP 工具（强制）

业务操作只能调 `tools/list` 列出的 qtou 工具：不自己读取 key，不用 curl / 脚本 / fetch 调 `/api/v1/agent/**`，不直连数据库，不读服务器本地文件。连不上或缺工具时如实报错并停止；客户端缓存了旧工具列表时先重连再查。stdio 代理的 `tools/list` 读取随包目录，不访问网络；没有可用 key 时业务调用返回 `-32001` / `AUTH_REQUIRED`，不向业务接口发请求。

## 工具

名称和入参以 `tools/list` 的随包目录为准（源提交 `877e4ad9eb8f8435c30b55b12949268d0cb24e30`）。

| 场景 | 工具 |
|---|---|
| 通用 | `agent_health` · `agent_dicts` |
| BP 入池 | `agent_bp_parse` · `agent_projects_create_pending` · `agent_projects_get` · `agent_projects_confirm` · `agent_projects_reject` · `agent_projects_user_fields` · `agent_projects_bp_schema` · `agent_projects_bp_get` · `agent_projects_bp_source` · `agent_projects_bp_fill` · `agent_projects_bp_attach` · `agent_projects_bp_pages` · `agent_projects_bp_assets` · `agent_projects_profile_get` · `agent_projects_profile_fill` |
| 尽调报告 | `agent_documents_search` · `agent_documents_content` · `agent_documents_pages` |
| 投后预警 | `agent_portfolio_list` · `agent_portfolio_quarterly` · `agent_risk_alerts_list` · `agent_risk_alerts_create` · `create_risk_draft` · `list_risk_drafts` · `dismiss_risk_draft` · `risk_drafts_summary` · `risk_run_record` · `risk_tyc_news` · `risk_config_get` · `risk_config_update` |

写操作都要用户确认：入池要过确认卡（见 `qtou-bp-intake`），预警逐条确认（见 `qtou-risk-alert`）。用户确认入池后的补空值写入按 `qtou-bp-intake` 自动执行，不再逐项确认。

## 返回与错误

- 列表类工具（`agent_documents_search`、`agent_portfolio_list`、`agent_risk_alerts_list`、`agent_dicts`）返回 `{ items: [...] }`。`agent_portfolio_list`、`agent_risk_alerts_list`、`agent_documents_search` 分页：传 `page`（从 1 起）和 `pageSize`（1–50，默认 20），返回 `total`、`hasMore`；要全量时 `hasMore: true` 就继续翻。
- 失败返回 `isError: true`，正文 `{"error": {"code", "message", "tool"}}`。code 有 `INVALID_ARGUMENT`、`NOT_FOUND`、`FAILED_PRECONDITION`、`BACKEND_DB_ERROR`、`INTERNAL_ERROR`、`UPSTREAM_*`。把 code 和 message 如实告诉用户，带 `ref=…` 的一并给出（管理员凭它查日志）；不改走别的路径，也不写成「没找到」。
- 参数传 JSON 对象：对象传对象、数组传数组、数字传数字、`confirmed` 传布尔。`arguments` 被序列化成字符串会返回「参数 arguments 格式不对，应为对象」，改成对象重发即可。

## 不做

不手抄 PAT；不在聊天里要账号密码或 key；不拷贝他人 `~/.qtou`；不打开 bot 的 box 桌面代签页；不把代签/MCP 地址写成 `agent.bitilinks.cn` 或 `localhost` / `127.0.0.1`；不把 RequestUserForm 的 site 写成 IP 或 `localhost`（要用 `qtou.cn`）；不假设弹网页安全表单就能把密码交给本工具；不沿用其他 bot 的 secret-request；不直连业务库；不空参赌 MCP elicitation；调工具不把参数对象、数组、数字写成字符串。
