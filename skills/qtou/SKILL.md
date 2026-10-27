---
name: qtou
description: >-
  连接并使用轻投：MCP 地址与鉴权、弹表单收账密代签 agent_key（前缀 qtpat_）、三场景（入池/尽调/预警）工具与 demo。
  用户说连轻投、装轻投 MCP、入池、尽调、风险预警时用。
---
# 轻投

同事 bot / Agent 安装本插件后，用户说「连轻投 / 装轻投 MCP / BP 入池 / 查文档尽调 / 投后预警」即按下列执行。

## MCP

| 项 | 值 |
| --- | --- |
| URL（开发占位） | `http://127.0.0.1:8081/api/v1/agent/mcp` |
| 传输 | Streamable HTTP |
| 鉴权 | `Authorization: Bearer <agent_key>` |
| 连接器名 | `轻投` |
| 插件变量 | `QTOU_CONNECTOR_TOKEN` |

只认 Bearer `agent_key`（由 `POST /v1/agent/auth/login` 签发），不读 cookie。无效/吊销 → 401（或业务码 `10007`）。

签发：弹表单收**用户名/密码**（不收 PAT）→ 代调 `POST http://127.0.0.1:8081/api/v1/agent/auth/login` → 得窄 scope 一次性 `agentKey` → 写入连接器 / 插件变量 `QTOU_CONNECTOR_TOKEN`。审计不写密码明文；key **永不**进聊天。

兼容别名：`POST /v1/agent/tokens` 行为与 login 一致（见三场景 AC0）。

装连接器（Grok Bot）：`AddMcpServer` → name `轻投`，url 同上，headers `Authorization: Bearer <token>`（token 来自代签结果写入的变量，勿手贴）。本插件在 Cursor 里通过 `mcp.json` + 变量 `QTOU_CONNECTOR_TOKEN` 注入。

> **注意：** 旧本机 `qtou-mcp`（`:8787` 只读 8 工具）**不是**本 Marketplace 成品，不得当作已交付连接器。

## 接入（强制）

禁止用户手抄/手填/粘贴 PAT / agent_key 到聊天。禁止引导「去设置页复制 token」作为主路径。

1. 已连接且冒烟工具（如 `agent_documents_search` 或 `agent_portfolio_list`）通则结束。
2. 未装或 401：主动说明要轻投**账密** → Vault 或安全表单（勿往聊天贴密码）。
3. 代登录 → 签发 agent_key → 写入连接器 / 插件变量。
4. 冒烟只读工具；key 永不进聊天。
5. 错密不签发；说明失败原因后可重试表单。

## 工具（MCP 转发 Agent API；最小集）

工具只走轻投 Agent API（经 `POST /v1/agent/mcp` 门面），**禁止**插件直连业务库。

| 工具名（与 `AgentMcpService` 一致） | 场景 | 用途 | 语义 |
| --- | --- | --- | --- |
| `agent_health` | — | 健康检查（确认 Bearer 有效） | 只读 |
| `agent_bp_parse` | ① | 解析 BP 文本为结构化草稿（不入库） | 只读 |
| `agent_projects_create_pending` | ① | 创建待确认项目（不直接入池） | **待确认** |
| `agent_projects_get` | ① | 查询待确认项目 | 只读 |
| `agent_documents_search` | ② | 模糊查文档 | 只读 |
| `agent_portfolio_list` | ③ | 投后/项目列表 | 只读 |
| `agent_risk_alerts_list` | ③ | 风险预警列表 | 只读 |
| `agent_dicts` | — | 字典 `invest_round` / `industry_type` | 只读 |

> 当前门面**未**暴露 `documents_content` / `dd_draft` / `portfolio_quarterly` / `risk_alerts_create` / `projects_confirm`；skill 演示只用上表已实现工具。写操作保持「待确认」语义；人确认入池若需 HTTP 确认口，另走 Agent API 非 MCP（待门面补齐）。

写操作一律保持「待确认」：先展示将写入的内容，用户明确同意后再调确认类工具。

## Demo（对话 → 工具）

### 连上

- 用户：「帮我连轻投」
- Bot：检查连接器 `轻投` → 未通则弹表单收账密 → `POST /v1/agent/auth/login` 签发 → 写入 `QTOU_CONNECTOR_TOKEN` / 装 MCP → 「已连上，可以入池 / 查文档 / 看投后了。」（不展示 key）

### ① BP 入池（最小）

- 用户：「把这段 BP 解析一下，准备入池」
- Bot：`agent_bp_parse` → 展示 projectName/round/industry → 用户确认后 `agent_projects_create_pending` → 用 `agent_projects_get` 核对；说明未确认前不进正式池（MCP 暂无 confirm 工具）。

### ② 模糊查文档 → 尽调初稿（最小）

- 用户：「搜一下云道的 BP，出个尽调初稿」
- Bot：`agent_documents_search({ q: "云道" })` → 展示命中列表；内容拉取/尽调初稿待门面补工具后再接。

### ③ 投后季报 → 风险预警（最小）

- 用户：「青云智行最近季报怎样？要不要记一条政策风险」
- Bot：`agent_portfolio_list` 找项目 → `agent_risk_alerts_list` 只读预警；季报/写预警待门面补齐。

## 不做

- 不引导设置页复制 token / 手抄 PAT 到聊天
- 不直连 MySQL / 业务库；不把旧 `qtou-mcp:8787` 当成品
- 不把 pending 项目直接写成正式池（须确认）
- 不做 COS 签名下载、外部舆情/工商新源、LLM 替换规则解析（Out）
- 不与工场插件抢名：连接器名 `轻投`、变量 `QTOU_CONNECTOR_TOKEN`（工场为 `智能体工场` / `AF_CONNECTOR_TOKEN`）

## 给 bot 的安装提示词

用户或群主可把下面整段发给 bot（Grok Bot / 开发助手），由其代装本地插件并走鉴权闭环：

```text
请按轻投 Cursor 插件本地树帮我装好并连上：

1. 源目录：/workspace/qtou-plugin/（或已同步的同内容仓）
2. 复制到本机：~/.cursor/plugins/local/qtou-plugin
3. Cursor Reload Window；确认 Customize 里可见插件「qtou / 轻投」与 skill「qtou」
4. 我说「连轻投」时：弹安全表单收轻投用户名/密码（不要收 PAT）
5. 代调 POST http://127.0.0.1:8081/api/v1/agent/auth/login → 得 agentKey
6. 写入插件变量 QTOU_CONNECTOR_TOKEN（或 AddMcpServer name=轻投，
   url=http://127.0.0.1:8081/api/v1/agent/mcp，Authorization: Bearer <key>）
7. 冒烟：agent_documents_search 或 agent_portfolio_list；成功只回「已连上」短句
8. 禁止：让我手抄/粘贴 PAT；禁止把 key 打进聊天；禁止用旧 qtou-mcp:8787 冒充成品
```

开发机 WAR 未起时：先按 `/workspace/qtou/DEV-STACK.md` 起 API（目标 `:8081/api`），MCP 门面就绪后再冒烟；门面未上线前可说明「插件树已装，MCP URL 占位待 QP2」。
