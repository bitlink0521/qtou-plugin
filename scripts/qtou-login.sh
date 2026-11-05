#!/bin/bash
# Sign a qtou connector key for Codex: asks for the qtou username/password (password hidden), calls the
# agent login on $QTOU_API (default: the 74 server) and stores ONLY the returned key in ~/.qtou/connector-token (mode 600).
# New terminals pick it up via the line this script adds to ~/.zshrc. Revoke: rerun, or delete the file.
set -euo pipefail
QTOU_API="${QTOU_API:-http://113.250.189.74:18081}"
read -r -p "轻投用户名: " QTOU_USER
read -r -s -p "轻投密码（不显示）: " QTOU_PASS; echo
mkdir -p ~/.qtou && chmod 700 ~/.qtou
QTOU_API="$QTOU_API" QTOU_USER="$QTOU_USER" QTOU_PASS="$QTOU_PASS" python3 - <<'PY'
import json, os, urllib.parse, urllib.request
body = urllib.parse.urlencode({"username": os.environ["QTOU_USER"], "password": os.environ["QTOU_PASS"], "client": "codex-cli"}).encode()
data = json.load(urllib.request.urlopen(urllib.request.Request(os.environ["QTOU_API"] + "/api/v1/agent/auth/login", data=body, method="POST"), timeout=20))
d = data.get("data") or data
key = d.get("agentKey") or ""
if not key.startswith("qtpat_"):
    raise SystemExit("登录失败：" + str(d.get("msg") or d.get("message") or "未返回连接 key"))
path = os.path.expanduser("~/.qtou/connector-token")
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.write(fd, key.encode()); os.close(fd)
print("已签发连接 key：" + str(d.get("agentKeyId")) + "（key 本身未显示）")
PY
unset QTOU_PASS
LINE='[ -f ~/.qtou/connector-token ] && export QTOU_CONNECTOR_TOKEN="$(cat ~/.qtou/connector-token)"'
grep -qxF "$LINE" ~/.zshrc 2>/dev/null || echo "$LINE" >> ~/.zshrc
launchctl setenv QTOU_CONNECTOR_TOKEN "$(cat ~/.qtou/connector-token)"
echo "完成。新开终端或重启 Codex 桌面版即可使用轻投。"
