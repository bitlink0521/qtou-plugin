# 轻投（Cursor Plugin）

连接轻投 Agent API：三场景 MCP（入池 / 尽调 / 预警）+ Agent 技能（含账密代签 `agent_key` 流程）。

形态对标 [智能体工场 Cursor 插件](../agent-factory-cursor-plugin/)（skill + MCP + logo）；**本目录为本地树**，尚未声明已发 Cursor Marketplace。

作者联系：`support@handsels.com`（Bitilinks / bitlink0521）。

## 包含

| 路径 | 说明 |
| --- | --- |
| `.cursor-plugin/plugin.json` | 显示名关键词含「轻投」；变量 `QTOU_CONNECTOR_TOKEN` |
| `mcp.json` | 连接器名 **轻投**；开发 URL `http://127.0.0.1:8081/api/v1/agent/mcp`；`Bearer ${QTOU_CONNECTOR_TOKEN}` |
| `skills/qtou/SKILL.md` | 连轻投、禁手抄、三场景各 1 demo、「不做」、**给 bot 的安装提示词** |
| `assets/logo.svg` | 占位标（青绿改色，**待换品牌**） |

## 本地试用

1. 复制本目录到 `~/.cursor/plugins/local/qtou-plugin`
2. Cursor 里 Reload Window
3. Customize 确认插件与技能 `qtou`；Configure **不要**手填令牌到聊天
4. 对 bot 说「连轻投」：按其 skill 弹表单收账密 → 代签 → 写入 `QTOU_CONNECTOR_TOKEN`

也可把 `skills/qtou/SKILL.md` 末尾「给 bot 的安装提示词」整段发给 bot 代装。

## 鉴权约定

- **禁止**用户手抄 / 粘贴 PAT / `agent_key` 到聊天；**禁止**以「去设置页复制 token」为主路径。
- 主路径：账密 → `POST /v1/agent/auth/login`（兼容 `/v1/agent/tokens`）→ 签发前缀 **`qtpat_`** 的窄 scope 凭证 → 写入 `QTOU_CONNECTOR_TOKEN`。
- MCP 只认 `Authorization: Bearer <qtpat_…>`，不读 cookie；勿手抄进聊天。

## 与旧 qtou-mcp 的关系

本机历史目录 `/workspace/qtou/qtou-mcp`（默认 `:8787`，只读 8 工具）是**联调/只读旁路**，**不是** Marketplace 成品，不得冒充本插件已交付。成品 MCP 门面为 WAR 上的 `POST /v1/agent/mcp`（Streamable HTTP，Bearer `agent_key`），见 AC pack QP2。

## 开发 URL 说明

`mcp.json` 当前指向 box 开发栈目标基址（见 `/workspace/qtou/DEV-STACK.md`）：

```text
http://127.0.0.1:8081/api/v1/agent/mcp
```

公网生产 URL 另议，不算本包 FAIL。MCP 门面未上线时，插件树仍可本地装入；工具调用会失败直到 QP2 完成。

## 与工场并装

| | 轻投 | 智能体工场 |
| --- | --- | --- |
| 连接器名 | `轻投` | `智能体工场` |
| 变量 | `QTOU_CONNECTOR_TOKEN` | `AF_CONNECTOR_TOKEN` |
| skill 目录 | `skills/qtou` | `skills/agent-factory` |
| 本地插件目录名 | `qtou-plugin` | `agent-factory` |

名称与变量刻意错开，可并装不互相覆盖。

## 发布（尚未做）

- 推到公开 GitHub（建议 `bitlink0521/qtou-plugin`）后，再提交 [Marketplace](https://cursor.com/marketplace/publish)
- 或 Teams：Dashboard → Plugins & MCPs → 导入仓库
- **当前状态：本地树就绪；未发 Marketplace；未声称公网可用。**

## AC 对照

验收包：`/workspace/qtou/qa/AC-PACK-qtou-cursor-plugin-2026-10-27.md`（QP0–QP5）。  
本目录覆盖 **QP0 文案骨架 + QP1 形态 + QP3/QP4 skill 文案**；QP2 MCP 门面与 Tokens 补齐、QP5 干净环境实装另刀。
