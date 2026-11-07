# 维护说明

给改插件配置的人。使用方法在仓库根目录的 `README.md`。

## 默认入口

插件清单里的 MCP 都启动 `tools/qtou_mcp_proxy.py`。`tools/list` 读同目录的 `tools/qtou_tool_catalog.json`（32 个业务工具）再加上 4 个本机账号工具。

| 文件 | 约定 |
| --- | --- |
| `mcp.json`、`.codex-mcp.json` | `python3 ./tools/qtou_mcp_proxy.py`，`cwd` 为 `.`。这是本仓库里不依赖宿主变量的写法。 |
| `.grok-mcp.json` | `${CURSOR_PLUGIN_ROOT}`。`.cursor-plugin/plugin.json` 和 `.grok-plugin/plugin.json` 指向这个文件。 |
| `.mcp.json` | `${CLAUDE_PLUGIN_ROOT}`。 |

`examples/http-mcp.example.json` 是 HTTP 直连示例，由 `scripts/build_manifests.py` 从 `plugin-meta.json` 的 `mcpUrl` 生成。它不是插件标准路径。任何 `plugin.json` 都不引用它。

改名称、版本、描述或代理路径时，只改 `plugin-meta.json`，然后运行 `python3 scripts/build_manifests.py`。`tools/test_manifests.py` 检查生成结果是否和磁盘一致。

## 技能如何被清单指向

四个目录都在 `skills/`，`SKILL.md` 的 `name` 与目录名相同：`qtou-connect`、`qtou-bp-intake`、`qtou-dd-report`、`qtou-risk-alert`。

- Codex：`.codex-plugin/plugin.json` 的 `skills` 为 `./skills/`。
- Cursor：`.cursor-plugin/plugin.json` 同样是 `./skills/`。依据是本机已安装的 Tavily 插件清单使用该字段：`~/.cursor/plugins/cache/cursor-public/3165/79c8c7356fcb9f5da450dd60c6727881cc4434fd/.cursor-plugin/plugin.json` 含 `"skills": "./skills/"`。
- Claude：官方插件说明写明插件根目录的 `skills/` 会被扫描（每个技能一个 `<name>/SKILL.md`），`skills` 键是在默认目录之外再加目录。因此 `.claude-plugin/plugin.json` 不写 `skills`。说明页：`https://code.claude.com/docs/en/plugins-reference`。
- Grok：本仓库的 `.grok-plugin/plugin.json` 只按已有字段生成（含 `mcpServers`），没有另加 `skills` 字段。

清单指向技能目录，不等于某个客户端进程已经把技能加载进当前会话。

## 上游错误契约

业务调用遇到 HTTP 错误或 JSON-RPC error 时，返回数值 `error.code`（不是整数则用 `-32002`）和固定句「轻投服务拒绝了这次调用」或「轻投服务返回 HTTP <状态码>」。不复制上游的 `message`、`data` 或原始正文。因此 6 位密码、嵌套 token、Bearer 值和环境变量密码即使被上游回显，也不会进入返回值或日志。

宿主 `initialize` 只在本地立即回答，不访问网络。客户端随后的 `notifications/initialized` 在上游会话尚未建立时不转发。第一次业务调用才按顺序发送已保存的 `initialize`、`notifications/initialized`，然后再发送这次业务调用。

## 安装命令从哪来

`README.md` 里的 Codex 两条命令和 Grok CLI 命令，与本仓库 `50036a9` 的用户说明相同：

```bash
codex plugin marketplace add bitlink0521/qtou-plugin
codex plugin add qtou@qtou-plugin
grok plugin install https://github.com/bitlink0521/qtou-plugin --trust
```

本环境没有 `codex` 和 `grok` 可执行文件，没有重跑 `--help`。
