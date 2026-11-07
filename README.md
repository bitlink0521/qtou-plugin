# 轻投插件

连接轻投，帮你做三件事：把商业计划书入池、按项目资料写尽调报告初稿、按阈值看投后风险。版本 **0.3.5**。需要本机 Python 3.7 或更高版本。

作者 Bitilinks（support@handsels.com）。产品页 `https://qtou.cn`。仓库 `https://github.com/bitlink0521/qtou-plugin`。许可证以 `plugin-meta.json` 的 MIT 声明为准。

## 能做什么

插件带 4 个技能和 36 个工具。技能告诉 AI 每件事的步骤；工具负责读、写轻投。

| 技能 | 什么时候用 |
| --- | --- |
| `qtou-connect` | 登录、切换账号、退出 |
| `qtou-bp-intake` | 把一份商业计划书入池 |
| `qtou-dd-report` | 按项目资料写尽调报告初稿 |
| `qtou-risk-alert` | 查看投后项目的财务、舆情和公告，并在你确认后写入预警 |

36 个工具里，32 个是轻投业务工具，4 个是本机账号工具（`qtou_account_list`、`qtou_account_add`、`qtou_account_switch`、`qtou_account_logout`）。业务工具按上面三件事分组：入池、查文档和写尽调、投后名单与预警。名称和入参以客户端里的工具列表为准。

## 安装

先克隆仓库：

```bash
git clone https://github.com/bitlink0521/qtou-plugin.git
cd qtou-plugin
python3 -c 'import sys; assert sys.version_info >= (3, 7)'
```

下面把 `<插件目录>` 换成你克隆下来的实际路径。

### Grok Bot

在插件市场搜索 **qtou** 并安装。装好后按下面「登录」用安全表单登录。不要自己改连接脚本，也不要手填连接 token。

市场里看到的版本以安装当时的市场页面为准。GitHub 上刚发布的版本不一定马上出现在市场里。

### Codex

```bash
codex plugin marketplace add bitlink0521/qtou-plugin
codex plugin add qtou@qtou-plugin
```

更新：`codex plugin marketplace upgrade qtou-plugin`

### Grok 命令行

```bash
grok plugin install https://github.com/bitlink0521/qtou-plugin --trust
```

更新：`grok plugin update`

### 其他客户端

在该客户端的 MCP 配置里加入（路径用你的 `<插件目录>`）：

```json
{
  "mcpServers": {
    "qtou": {
      "command": "python3",
      "args": ["<插件目录>/tools/qtou_mcp_proxy.py"],
      "env": {
        "PYTHONPATH": "<插件目录>/tools"
      }
    }
  }
}
```

保存后重新连接这个 MCP。

技能在 `<插件目录>/skills/` 下的四个目录：`qtou-connect`、`qtou-bp-intake`、`qtou-dd-report`、`qtou-risk-alert`。每个目录里有同名的 `SKILL.md`。Codex 和 Cursor 的插件清单把技能目录写成 `./skills/`。Claude 插件读取插件根目录下的 `skills/`。如果某个客户端要单独添加技能，把这四个目录加到它的技能位置。

## 登录

第一次用业务工具之前需要登录。对 AI 说「登录轻投」。

AI 必须用**当前这次聊天的安全表单或掩码输入**，或这个客户端自己的安全登录来接收账号。不要在对话正文里打出密码，也不要接受 AI 让你把密码贴进消息。登录只应出现在安全输入里。完成后账号保存在本机，以后这台机器上的轻投操作直接用它。

可以说：添加轻投账号、切换到某个账号、现在用的哪个账号、退出某个账号。

## 三件事怎么开始

登录之后直接说人话即可。

- **入池**：把商业计划书发给 AI，说「把这份 BP 入池」。AI 会先给你一张确认卡，你同意之后才写入。
- **尽调**：说「按某某项目的资料写一份尽调报告初稿」。这一步只读资料，不改轻投里的数据。
- **投后风险**：说「看看投后项目有没有要处理的风险」。写入预警之前，AI 会逐条请你确认。

业务数据在轻投服务上。默认地址是 `http://113.250.189.74:18081/api/v1/agent/mcp`。写入是否成功，以轻投返回的结果为准。
