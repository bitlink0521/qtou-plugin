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
4. 冒烟：documents_search 或 portfolio_list 通即可回报。不要让我手填 MCP URL。
```

### 人工备用路径

- **团队市场**：Dashboard → Plugins & MCPs → Import from Repo，填 `https://github.com/bitlink0521/qtou-plugin`。
- **本机**：把本仓拷到 `~/.cursor/plugins/local/qtou-plugin`，在 Cursor 里 Reload Window。

拷好后仍把上面的提示词发给 bot，由它收账密、代签并写入 `QTOU_CONNECTOR_TOKEN`。

### 官方 Marketplace

过审前，聊天里用 `/add-plugin` 粘贴本仓 GitHub URL 通常装不上。过审后改为 Marketplace 一键安装；在此之前用上面的 bot 安装或人工备用路径。

## 包含

- **Logo**：`assets/logo.svg`
- **Skill**：`skills/qtou`（连轻投、三场景 demo；含代签 agent_key）
- **MCP**：`mcp.json` → 连接器名 **轻投**（随插件生效，不必手填 URL）
- **变量**：`QTOU_CONNECTOR_TOKEN`（Bearer `qtpat_…`，由 bot 写入插件变量；勿贴到聊天）

## 鉴权约定

禁止用户手抄 PAT / agent_key 到聊天。优先账密登录 → 签发窄 scope 凭证 → 写入连接器 / 插件变量。只认 Bearer，不读 cookie。
