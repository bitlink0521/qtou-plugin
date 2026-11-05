#!/bin/bash
# Sign a qtou connector key: collects the qtou username/password, calls the agent login on $QTOU_API
# (default: the 74 server) and stores ONLY the returned key in ~/.qtou/connector-token (mode 600).
# Without a terminal (e.g. run by Codex) the credentials are collected with macOS dialogs, so the password
# never passes through the chat or the model. New terminals pick the key up via ~/.zshrc; desktop apps via
# launchctl. Revoke: rerun, or delete the file.
set -euo pipefail
QTOU_API="${QTOU_API:-http://113.250.189.74:18081}"

ask_dialog() {
  local prompt=$1 hidden=$2
  osascript -e "text returned of (display dialog \"$prompt\" default answer \"\" $hidden with title \"连接轻投\" buttons {\"取消\", \"登录\"} default button \"登录\" cancel button \"取消\")" 2>/dev/null \
    || { echo "已取消登录。" >&2; exit 1; }
}

if [ "${1:-}" = "--gui" ] || [ ! -t 0 ]; then
  command -v osascript >/dev/null || { echo "没有终端也没有 macOS 对话框，请在终端里运行本脚本。" >&2; exit 1; }
  QTOU_USER=$(ask_dialog "轻投用户名" "")
  QTOU_PASS=$(ask_dialog "轻投密码" "with hidden answer")
else
  read -r -p "轻投用户名: " QTOU_USER
  read -r -s -p "轻投密码（不显示）: " QTOU_PASS; echo
fi

mkdir -p ~/.qtou && chmod 700 ~/.qtou
QTOU_API="$QTOU_API" QTOU_USER="$QTOU_USER" QTOU_PASS="$QTOU_PASS" python3 - <<'PY'
import json, os, urllib.error, urllib.parse, urllib.request
body = urllib.parse.urlencode({"username": os.environ["QTOU_USER"], "password": os.environ["QTOU_PASS"], "client": "qtou-login"}).encode()
try:
    data = json.load(urllib.request.urlopen(urllib.request.Request(os.environ["QTOU_API"] + "/api/v1/agent/auth/login", data=body, method="POST"), timeout=20))
except urllib.error.URLError as error:
    raise SystemExit("连不上轻投服务：" + str(getattr(error, "reason", error)))
d = data.get("data") or data
key = d.get("agentKey") or ""
if not key.startswith("qtpat_"):
    raise SystemExit("登录失败：" + str(data.get("msg") or d.get("message") or "未返回连接 key"))
path = os.path.expanduser("~/.qtou/connector-token")
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.write(fd, key.encode()); os.close(fd)
print("已签发连接 key：" + str(d.get("agentKeyId")) + "（key 本身未显示）")
PY
unset QTOU_PASS
LINE='[ -f ~/.qtou/connector-token ] && export QTOU_CONNECTOR_TOKEN="$(cat ~/.qtou/connector-token)"'
grep -qxF "$LINE" ~/.zshrc 2>/dev/null || echo "$LINE" >> ~/.zshrc
launchctl setenv QTOU_CONNECTOR_TOKEN "$(cat ~/.qtou/connector-token)" 2>/dev/null || true
echo "完成。请重启 Codex（桌面版退出重开，命令行新开终端）后即可使用轻投。"
