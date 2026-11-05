# 轻投（Cursor Plugin）

本插件 = Skill + MCP + Logo，连接轻投 Agent API（入池 / 尽调 / 预警）。

官方 Marketplace 可能尚未过审。同事请走下面的快捷安装，不要手填 MCP 地址，也不要把 `qtpat_…` 贴进聊天。

## 同事快捷安装

### 复制这段发给 bot

把下面整段复制，发给自己的 Cursor / Grok Bot。bot 会自己装插件、收账密、代签并做冒烟。

```text
安装并连上轻投，做完再回报。

1. 从本公开仓安装插件。优先团队市场 Import from Repo：https://github.com/bitlink0521/qtou-plugin
   若无团队市场：把仓库拷到 ~/.cursor/plugins/local/qtou-plugin，然后 Reload Window。
2. 装好后按插件 skill：弹表单收轻投账密 → 代登录签发 agent_key（前缀 qtpat_）→ 写入连接器/插件变量 QTOU_CONNECTOR_TOKEN。
3. 禁止让我手抄或粘贴 qtpat_… 到聊天。
4. 冒烟：agent_documents_search 或 agent_portfolio_list 通即可回报。不要让我手填 MCP URL。
```

### 人工备用路径

- **团队市场**：Dashboard → Plugins & MCPs → Import from Repo，填 `https://github.com/bitlink0521/qtou-plugin`。
- **本机**：把本仓拷到 `~/.cursor/plugins/local/qtou-plugin`，在 Cursor 里 Reload Window。

拷好后仍把上面的提示词发给 bot，由它收账密、代签并写入 `QTOU_CONNECTOR_TOKEN`。

### 官方 Marketplace

过审前，聊天里用 `/add-plugin` 粘贴本仓 GitHub URL 通常装不上。过审后改为 Marketplace 一键安装；在此之前用上面的 bot 安装或人工备用路径。

## Codex 安装

```bash
codex plugin marketplace add bitlink0521/qtou-plugin
codex plugin add qtou@qtou-plugin
```

第一次用轻投时 Codex 会弹出登录表单，填轻投用户名和密码即可（表单内容只交给插件，不进聊天）。登录信息保存在本机 `~/.qtou/`，以后直接用；登录失效会再弹一次。支持多个账号：在 Codex 里说「添加轻投账号」「切换到 xx 账号」「现在用的哪个轻投账号」「退出轻投账号」即可。需要本机有 `python3`。以后更新插件：`codex plugin marketplace upgrade qtou-plugin`。

## 包含

- **Logo**：`assets/logo.png`（轻投标志）
- **技能（4 个）**：
  - `qtou-connect`：连接、登录、多账号（添加/切换/退出）、工具清单与通用规则
  - `qtou-bp-intake`：BP 入池，确认卡后自动补全字段（含 `PROJECT-ENRICHMENT.md`、`BP-VISUALS.md`）
  - `qtou-dd-report`：检索文档写尽调报告初稿（含 `DD-REPORT-WRITING.md`）
  - `qtou-risk-alert`：投后风险预警，员工确认后回写
- **MCP**：`mcp.json`（Cursor）/ `.codex-mcp.json`（Codex，经 `qtou_mcp_proxy.py` 自动登录）→ 连接器名 **qtou**（随插件生效，不必手填 URL）
- **变量**：`QTOU_CONNECTOR_TOKEN`（Bearer `qtpat_…`，由 bot 写入插件变量；勿贴到聊天）

## 鉴权约定

禁止用户手抄 PAT / agent_key 到聊天。优先账密登录 → 签发窄 scope 凭证 → 写入连接器 / 插件变量。只认 Bearer，不读 cookie。

## 维护

- 名称、版本、描述、logo、MCP 地址只改 `plugin-meta.json`，然后运行 `python3 scripts/build_manifests.py` 生成各客户端的清单（Codex、Cursor、Claude/WorkBuddy、Grok）和 MCP 配置；`tools/test_manifests.py` 会检查是否同步。
- 工具脚本共用 `tools/qtou_shared.py`（HTTP、Tavily、Grok、本机账号存储），新脚本不要再各写一份。
