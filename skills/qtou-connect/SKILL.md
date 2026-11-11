---
name: qtou-connect
description: >-
  连接轻投（qtou）：浏览器登录、换账号、工具清单与通用返回/错误约定。
  用户说连轻投、装轻投、登录轻投、换轻投账号、退出轻投，或其他轻投技能需要先连上时用。
---
# 轻投：连接与账号

## 连接

所有客户端（Codex、Claude Code、WorkBuddy、Grok Bot）都直连 `https://qtou.handsels.com/api/v1/agent/mcp`，在浏览器里登录轻投，不需要 Python，也没有 `qtou_account_*` 工具。

- 第一次使用时客户端会弹出（或给出链接打开）轻投登录页，用户在浏览器里输入轻投账号密码即可。登录后页面自动关闭，或提示「回到客户端」，浏览器询问是否打开应用时选「打开」。
- 账号密码只在轻投登录页里填，**不要在聊天里要密码**，也不要让用户把 key 发到对话里。
- 对话里没有任何轻投工具、或工具返回 401：请用户在客户端的 MCP / 连接器设置里找到「qtou」（Grok 上可能叫「轻投」）点登录（Authenticate / Connect）。命令行：Codex `codex mcp login qtou`；Claude Code 在对话里输入 `/mcp` 选 qtou 登录。登录后新开一个对话。
- 换账号：在同一处退出轻投登录（Codex 命令行 `codex mcp logout qtou`），再用另一个账号登录。正在做入池确认、预警确认等多步操作时先提醒用户：待确认记录属于原账号，要切回去才能继续。
- 现在登录的是谁：调 `agent_health`。

| 项 | 值 |
| --- | --- |
| MCP 地址 | `https://qtou.handsels.com/api/v1/agent/mcp`（禁止写成 `agent.bitilinks.cn` 或 `localhost` / `127.0.0.1`） |
| 传输 | Streamable HTTP |
| 登录 | OAuth 2.1（浏览器登录，客户端自动注册） |
| 连接器名 | `qtou`（Grok 上手工添加的可能叫 `轻投`，二者等价） |

## 只走 MCP 工具（强制）

业务操作只能调已连接的 qtou 工具：不自己读取 key，不用 curl / 脚本 / fetch 调 `/api/v1/agent/**`，不直连数据库，不读服务器本地文件。连不上或缺工具时如实报错并停止；客户端缓存了旧工具列表时先重连再查。例外只有工具返回的一次性地址：上传 BP（`agent_projects_bp_upload_url`）、上传待转换文件（`agent_files_convert_url`）、下载转好的 PDF（`pdfUrl`）和页面图（`imageUrl`），用 curl 按返回说明调用。尽调报告的 Word 由服务端工具 `agent_report_word` 生成，返回的下载链接交给用户在浏览器里点。

## 工具

| 场景 | 工具 |
|---|---|
| 通用 | `agent_health` · `agent_dicts` · `agent_files_convert_url`（PPT、Word 等转 PDF） |
| BP 入池 | `agent_bp_parse` · `agent_projects_create_pending` · `agent_projects_find` · `agent_projects_financing_add` · `agent_projects_get` · `agent_projects_company_choose` · `agent_projects_confirm` · `agent_projects_reject` · `agent_projects_user_fields` · `agent_projects_bp_schema` · `agent_projects_bp_get` · `agent_projects_bp_source` · `agent_projects_bp_fill` · `agent_projects_bp_upload_url` · `agent_projects_bp_attach` · `agent_projects_bp_pages` · `agent_projects_bp_assets` · `agent_projects_web_logo` · `agent_projects_profile_get` · `agent_projects_profile_fill` |
| 尽调报告 | `agent_documents_search` · `agent_documents_content` · `agent_documents_pages` · `agent_report_word`（服务端按站内范本生成 Word，返回下载链接） |
| 投后预警 | `agent_portfolio_list` · `agent_portfolio_quarterly` · `agent_risk_threshold_get` · `agent_risk_alerts_list` · `agent_risk_alerts_create` |

写操作都要用户确认：入池前在对话里给出确认卡、等用户回复「确认入池」（见 `qtou-bp-intake`），预警逐条在对话里确认（见 `qtou-risk-alert`）。客户端调用工具时若再弹「是否允许」，那是客户端自己的确认，照常让用户点。用户确认入池后的补空值写入按 `qtou-bp-intake` 自动执行，不再逐项确认。

## Windows 命令

技能里的命令按 Mac / Linux 写。Windows（PowerShell）对应：`curl` 写成 `curl.exe`（PowerShell 的 `curl` 是另一个命令）；`shasum -a 256 <文件>` 用 `(Get-FileHash <文件> -Algorithm SHA256).Hash.ToLower()`；`date -u +%Y-%m-%dT%H:%M:%SZ` 用 `(Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")`；`mdfind -name <文件名>` 用 `Get-ChildItem $HOME -Recurse -Filter <文件名> -ErrorAction SilentlyContinue`。

## 返回与错误

- 列表类工具（`agent_documents_search`、`agent_portfolio_list`、`agent_risk_alerts_list`、`agent_dicts`）返回 `{ items: [...] }`。`agent_portfolio_list`、`agent_risk_alerts_list`、`agent_documents_search` 分页：传 `page`（从 1 起）和 `pageSize`（1–50，默认 20），返回 `total`、`hasMore`；要全量时 `hasMore: true` 就继续翻。
- 失败返回 `isError: true`，正文 `{"error": {"code", "message", "tool"}}`。code 有 `INVALID_ARGUMENT`、`NOT_FOUND`、`FAILED_PRECONDITION`、`BACKEND_DB_ERROR`、`INTERNAL_ERROR`、`UPSTREAM_*`。把 code 和 message 如实告诉用户，带 `ref=…` 的一并给出（管理员凭它查日志）；不改走别的路径，也不写成「没找到」。
- 工具调用没拿到返回、报网络或传输错误（如 `error sending request`、连接被断开、超时）：多是长时间空闲后连接被网络断开，不是轻投的业务错误，原样重试同一调用（间隔几秒，最多 2 次）。写入类工具重试前先用对应的读取工具看一眼是否已经写进去，写进去了就不再重试。重试仍失败再如实告诉用户并停下。
- 读取类工具（名字以 `_get`、`_list`、`_find`、`_search`、`_pages` 结尾的，以及 `agent_projects_profile_get` 这类只读工具）返回 `BACKEND_DB_ERROR`：多人同时操作时偶发，隔几秒原样重试一次，仍失败再按上面转告并停下。写入类工具不这样重试。
- 参数传 JSON 对象：对象传对象、数组传数组、数字传数字、`confirmed` 传布尔。`arguments` 被序列化成字符串会返回「参数 arguments 格式不对，应为对象」，改成对象重发即可。

## 不做

不在聊天里要账号密码或 key；不手抄 PAT；不拷贝他人 `~/.qtou`；不把 MCP 地址写成 `agent.bitilinks.cn`（工场）或 `localhost` / `127.0.0.1`；不直连业务库；不与工场抢名；调工具不把参数对象、数组、数字写成字符串。
