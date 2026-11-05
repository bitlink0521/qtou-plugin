---
name: qtou-connect
description: >-
  连接轻投（qtou）：安装插件、登录与自动保存、多账号添加/切换/退出、MCP 鉴权规则、工具清单与通用返回/错误约定。
  用户说连轻投、装轻投、登录轻投、换轻投账号、退出轻投，或其他轻投技能需要先连上时用。
---
# 轻投：连接与账号

## 接入（强制）

1. 已连且冒烟（`agent_health`）通则结束。
2. Codex：插件的 `qtou` 连接由插件根目录 `tools/qtou_mcp_proxy.py` 启动。没有可用账号或 key 失效时，它自己请 Codex 弹出登录表单（不支持表单的客户端改用 macOS 对话框），签发后保存，之后自动复用。表单内容只回给启动器，不进聊天；不要在聊天里要账密。若工具返回「未登录轻投：已取消登录」，告诉用户再发一次请求、在表单里登录即可。
3. 其他客户端（Grok / Cursor）：未装或 401 时弹表单收轻投账密 → 代签 → 写入变量 `QTOU_CONNECTOR_TOKEN` → 冒烟只读工具。

## 多账号（Codex 插件）

启动器在轻投工具之外提供 4 个本地工具，账号信息只存在本机 `~/.qtou/`（权限 600），不经过服务端以外的任何地方：

- `qtou_account_list`：列出本机已登录的轻投账号，标出当前账号。用户问「现在用的哪个账号」时调它。
- `qtou_account_add`：弹登录表单添加一个账号，登录成功后切换为当前账号。
- `qtou_account_switch({ username })`：切换当前账号；之后所有轻投操作都以该账号身份进行。
- `qtou_account_logout({ username? })`：退出账号（不传则退出当前账号），同时在服务端吊销该账号的 key。

切换或退出前，如果正在进行入池确认、预警确认等多步操作，先提醒用户：换账号后待确认记录属于原账号，需要切回去才能继续。不要替用户决定切换到哪个账号。

## MCP 与鉴权

| 项 | 值 |
| --- | --- |
| URL | `<QTOU_MCP_URL>`（由 G02 的 qtou-login 安装时写入实际地址；正式域名部署时再定） |
| 传输 | Streamable HTTP |
| 鉴权 | `Authorization: Bearer <agent_key>` |
| 连接器名 | `qtou`（Grok 上手工添加的可能叫 `轻投`，二者等价） |
| 插件变量 | `QTOU_CONNECTOR_TOKEN` |

只认 Bearer `agent_key`（由 `POST /v1/agent/auth/login` 签发），不读 cookie。无效/吊销 → 401（或业务码 `10007`）。

签发：弹表单收账密（不收 PAT）→ 代调 `POST /api/v1/agent/auth/login`（与 MCP 同主机）→ 得窄 scope `agentKey` → 写入 `QTOU_CONNECTOR_TOKEN`。审计不写密码明文；key 永不进聊天。兼容别名 `POST /v1/agent/tokens`。

装连接器：优先团队市场 / Marketplace 插件 qtou。Grok Bot 上若 `轻投` 报 Network error，改用 stdio 等价连接器（`轻投stdio` / `轻投本地`）。禁止手填 URL、禁止手抄 PAT。

旧的独立 qtou-mcp 服务不是成品，只认插件配置的 `<QTOU_MCP_URL>`。

**禁止直调 HTTP（强制）**：除上面「签发」这一步把账密换成 key、并直接写入 `QTOU_CONNECTOR_TOKEN` 以外，模型不得自己读取 `agent_key` / `QTOU_CONNECTOR_TOKEN`（不读插件变量、配置文件、环境变量、钥匙串），不得拿它用 curl / 脚本 / fetch 直接调 `/api/v1/agent/**` 任何接口（含 confirm、reject、写入类接口）。一切业务操作只走 MCP 工具。不得用 curl、脚本等自行调用 MCP 端点或 REST 接口，只能通过已配置的连接器工具。MCP 连不上或缺工具时，如实报错并停止，不改用 HTTP、不直连库。服务端审计会把不经 MCP 的直调请求单独标出（`direct_http=true`）。唯一例外是 `agent_projects_bp_upload_url` 发回的一次性上传地址（见 `qtou-bp-intake` 技能「入池后自动补全」），它不带也不收 key。

## 工具最小集（14 个）

`agent_health` · `agent_bp_parse` · `agent_projects_create_pending` · `agent_projects_get` · `agent_projects_confirm` · `agent_projects_reject` · `agent_documents_search` · `agent_documents_content` · `agent_documents_pages` · `agent_portfolio_list` · `agent_portfolio_quarterly` · `agent_risk_alerts_list` · `agent_risk_alerts_create` · `agent_dicts`

入池补全另用：`agent_projects_bp_schema` · `agent_projects_bp_get` · `agent_projects_bp_fill` · `agent_projects_bp_upload_url` · `agent_projects_bp_attach` · `agent_projects_bp_pages` · `agent_projects_bp_assets` · `agent_projects_bp_source` · `agent_projects_profile_get` · `agent_projects_profile_fill`（见 `qtou-bp-intake` 技能）。

若连接器工具列表里没有 `agent_documents_content`，是客户端缓存了旧列表：先重连 / 重启该 MCP 再查；仍没有则报「服务端未部署 content」，不得改用别的路径读文件。
`agent_portfolio_quarterly` / `agent_risk_alerts_create` 缺失同理：重连后仍缺报「服务端未部署场景③工具」，不得改用 HTTP 或直连库。

写操作一律待确认，禁止静默入池。入池 confirm 必须带确认卡发出的 `confirmToken`，见 `qtou-bp-intake` 技能的 AC MC3。例外：用户已点「确认入池」的项目，其补空值类写入（bp_attach / bp_assets / bp_fill / profile_fill）按 `qtou-bp-intake` 技能「入池后自动补全」自动执行，不再逐项确认。

**返回形状与错误（2026-10-28 起，HTTP 与 stdio 一致）**：检索/列表类工具（`agent_documents_search` / `agent_portfolio_list` / `agent_risk_alerts_list` / `agent_dicts`）一律返回 `{ items: [...] }`，从 `items` 取。工具失败返回 `isError=true`，正文是 `{"error":{"code","message","tool"}}`。code 包括 `INVALID_ARGUMENT`、`NOT_FOUND`、`FAILED_PRECONDITION`、`BACKEND_DB_ERROR`、`INTERNAL_ERROR`，桥侧还有 `UPSTREAM_UNAVAILABLE` / `UPSTREAM_HTTP_*` / `UPSTREAM_RPC_*`。拿到这类返回时，把 code 和 message 如实告诉用户，不得重试成别的路径（HTTP、直连库、读本地文件），也不得写成「没找到」。message 已是给人看的中文说明，不含服务器路径和 Java 异常；带 `ref=…` 的表示详情只在服务端日志，转告用户时把 ref 一并给出，方便管理员查日志。（2026-10-28 s2c 起）`UPSTREAM_HTTP_*` / `UPSTREAM_BAD_RESPONSE` 等桥侧错误的 message 也带 `ref=…`，与桥 stderr 同一个；`NOT_FOUND` 只说什么不存在（如「项目不存在或不属于当前租户」「文件不存在」），不再回显传入的 id，需要时自己对照刚传的参数告诉用户。stdio 上 `arguments` 不是对象时返回 isError `INVALID_ARGUMENT`「参数 arguments 格式不对，应为对象」（与 HTTP 相同）；发出的行不是合法 JSON 会立刻收到 JSON-RPC `-32700`（id=null），不是 JSON-RPC 对象或 params 不是对象收到 `-32600`，桥不会断，修正后重发即可。（2026-10-28 s2d 起）桥 stderr 只记脱敏、截断后的摘要：令牌、Bearer、token/password/secret/cookie/agent_key 等字段值一律显示为 `***`，单行坏请求不超过 300 字符，上游原文不超过 800 字符。排障时用 ref 对照，不要指望在 stderr 里看到原始请求。

## 不做

不手抄 PAT；不在聊天里要账号密码；不直连业务库；不与工场抢名；调工具不把参数对象、数组、数字写成字符串。
