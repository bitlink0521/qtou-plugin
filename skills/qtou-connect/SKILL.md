---
name: qtou-connect
description: >-
  连接轻投（qtou）：登录与自动保存、多账号添加/切换/退出、鉴权规则、工具清单与通用返回/错误约定。
  用户说连轻投、装轻投、登录轻投、换轻投账号、退出轻投，或其他轻投技能需要先连上时用。
---
# 轻投：连接与账号

## 连接

1. 调 `agent_health`，通了就结束。
2. Codex、WorkBuddy、Grok 命令行：插件的 `qtou` 连接由插件根目录的 `tools/qtou_mcp_proxy.py` 启动。没有可用账号或 key 失效时，它会自己弹登录表单（不支持表单的客户端弹 macOS 对话框），登录后保存在本机 `~/.qtou/`，之后自动复用。表单内容只交给启动器，不进聊天，不要在聊天里要账号密码。工具返回「未登录轻投：已取消登录」时，告诉用户再发一次请求、在表单里登录。
3. 云端客户端（Grok Bot 等）：未登录或返回 401 时，用客户端的安全表单收轻投账号密码，调 `POST <MCP 同主机>/api/v1/agent/auth/login` 换取 `qtpat_` 开头的 key，写入插件变量 `QTOU_CONNECTOR_TOKEN`，再调 `agent_health` 冒烟。key 不进聊天、不打印。

## 多账号（插件启动器提供的本地工具）

- `qtou_account_list`：列出本机已登录的账号，标出当前账号。用户问「现在用的哪个账号」时调它。
- `qtou_account_add`：弹登录表单添加账号，成功后切换为当前账号。
- `qtou_account_switch({ username })`：切换当前账号。
- `qtou_account_logout({ username? })`：退出账号（不传则退出当前账号），同时在服务端吊销它的 key。

切换或退出前，如果正在做入池确认、预警确认等多步操作，先提醒用户：待确认记录属于原账号，要切回去才能继续。不替用户决定切到哪个账号。

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
