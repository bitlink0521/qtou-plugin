# 轻投插件

连接轻投，帮你做三件事：把商业计划书入池、按项目资料写尽调报告初稿、按阈值看投后风险。版本 **0.3.5**。需要本机 Python 3.7 或更高版本。

作者 Bitilinks（support@handsels.com）。产品页 `https://qtou.cn`。仓库 `https://github.com/bitlink0521/qtou-plugin`。许可证以 `plugin-meta.json` 的 MIT 声明为准。

## 三块职责

- **账号**在本机。四个工具：`qtou_account_list`、`qtou_account_add`、`qtou_account_switch`、`qtou_account_logout`。密码不要出现在聊天里。登录成功后账号保存在本机 `~/.qtou/`，不要把这个目录发给别人。
- **工具目录**随插件走。打开连接后就能看到 36 个工具（32 个轻投业务工具和上面 4 个账号工具），每个都有名称、说明和入参。这一步不需要登录，也不访问轻投。
- **业务调用**才连接轻投。没有登录时，业务工具不会发出去。登录之后，读和写都发到轻投；写入前按下面的确认步骤做。

## 安装

```bash
git clone https://github.com/bitlink0521/qtou-plugin.git
cd qtou-plugin
python3 -c 'import sys; assert sys.version_info >= (3, 7)'
```

把下面的 `<插件目录>` 换成克隆下来的实际路径。

### Grok Bot

在插件市场搜索 **qtou** 并安装。不要自己改连接脚本，也不要手填连接 token。装好后按「第一次使用」登录。

市场页面上的版本以安装当时显示的为准。GitHub 上的新版本不一定马上出现在市场里。

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

### 自己填写 MCP 配置

适用于要手动添加连接的客户端。这是本仓库默认配置所启动的同一个程序：

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

四个技能在 `<插件目录>/skills/`：`qtou-connect`（登录和账号）、`qtou-bp-intake`（入池）、`qtou-dd-report`（尽调初稿）、`qtou-risk-alert`（投后风险）。每个目录里有同名的 `SKILL.md`。

## 这次没有在客户端里验收的部分

本仓库核对了配置文件，并用打包后的目录启动了 `python3 tools/qtou_mcp_proxy.py`。没有在 Grok Bot、Codex、Claude、Cursor 里重新安装，也没有确认这些客户端的界面已经出现 4 个技能或 36 个工具。不能把「文件在仓库里」当成「你的客户端已经装好」。

Codex 与 Cursor 的插件清单写了技能目录 `./skills/`。Claude 的插件说明写的是默认读取插件根目录的 `skills/`。Grok 的清单没有单独的技能字段。这些都还没有在对应客户端里验收。

## 传输

当前写在程序里的默认地址是开发用的明文 HTTP：`http://113.250.189.74:18081/api/v1/agent/mcp` 和同主机的 `/api/v1/agent/auth/login`。密码和 key 会按这个地址发送。这次没有改成 HTTPS，也不能把传输说成已经安全。

公开发布前应改用可核验证书的 HTTPS。启动前设置：

```bash
export QTOU_MCP_URL='https://你的正式域名/api/v1/agent/mcp'
export QTOU_LOGIN_URL='https://你的正式域名/api/v1/agent/auth/login'
python3 -c 'import os; assert os.environ["QTOU_MCP_URL"].startswith("https://"); assert os.environ["QTOU_LOGIN_URL"].startswith("https://")'
```

这两条都不是 `https://` 时，不要把该配置交给公开用户。

## 第一次使用

1. 连上之后就可以看到 36 个工具。还没登录也可以看列表。
2. 登录只有两条不会把密码打进聊天的路：
   - 在你自己的终端执行 `python3 <插件目录>/tools/qtou_mcp_proxy.py --login`。程序只在这个终端能隐藏输入时询问密码。没有这种终端就直接退出，不会改用普通输入框。
   - 或者由客户端在**启动代理之前**把密码放进该进程的 `QTOU_LOGIN_PASSWORD`（用户名放进 `QTOU_LOGIN_USERNAME`）。代理已经在跑时，先重开这个连接，再让 AI 调用 `qtou_account_add`，调用参数里不要带密码。
3. 做不到上面任何一条，就停止。不要把密码打进对话。客户端里的普通文本框，包括 MCP 表单里的 string 字段，都不是掩码。
4. 登录后说「检查轻投连接」。这是只读检查，工具是 `agent_health`，不需要参数。

用户名参数不能搭配另一个账号留在环境里的密码。退出账号只删除本机保存的那个账号；如果当前只用了环境变量里的连接 token，退出会让本进程停止使用它，并请你在客户端去掉 `QTOU_CONNECTOR_TOKEN` 后重开连接。

账号相关可以说：现在用的哪个轻投账号、添加轻投账号、切换到某个账号、退出某个账号。

## 三件事怎么开始

- **入池**：把商业计划书发给 AI，说「把这份 BP 入池」。它会先给你确认，你同意之后才写入。
- **尽调**：说「按某某项目的资料写一份尽调报告初稿」。这一步只读资料。
- **投后风险**：说「看看投后项目有没有要处理的风险」。写入预警之前会逐条请你确认。

业务数据在轻投上，默认地址是 `http://113.250.189.74:18081/api/v1/agent/mcp`。有没有写成功，以轻投的返回为准。

## 出错时怎么做

- 还没登录就调用业务工具：先按上面的方式登录。这次调用不会发给轻投。
- 已经登录但轻投拒绝或暂时不可用：你会看到固定的一句说明（拒绝，或带 HTTP 状态码）。里面没有密码、key，也没有轻投返回的原文。可以稍后重试；如果一直失败，重新登录后再试。
