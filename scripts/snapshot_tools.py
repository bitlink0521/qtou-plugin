#!/usr/bin/env python3
"""Refresh tools/qtou_tools_snapshot.json from the live server using the current signed-in account.

The proxy lists these tools before the first login, so rerun this whenever the server's tool list changes.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import qtou_shared  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROXY = os.path.join(ROOT, 'tools', 'qtou_mcp_proxy.py')
SNAPSHOT = os.path.join(ROOT, 'tools', 'qtou_tools_snapshot.json')
LOCAL = {'qtou_account_list', 'qtou_account_add', 'qtou_account_switch', 'qtou_account_logout', 'qtou_report_word'}


def main():
    if not qtou_shared.current_token():
        sys.exit('本机没有登录轻投：先运行 python3 tools/qtou_mcp_proxy.py --login 再重跑。')
    requests = [
        {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
         'params': {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 'snapshot', 'version': '1'}}},
        {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
        {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
    ]
    proxy = subprocess.Popen([sys.executable, PROXY], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    for request in requests:
        proxy.stdin.write(json.dumps(request) + '\n')
    proxy.stdin.flush()
    for line in proxy.stdout:
        reply = json.loads(line)
        if reply.get('id') == 2:
            break
    proxy.kill()
    tools = [tool for tool in (reply.get('result') or {}).get('tools') or [] if tool.get('name') not in LOCAL]
    if not tools:
        sys.exit('没有拿到业务工具：先登录轻投（python3 tools/qtou_mcp_proxy.py --login）再重跑。')
    with open(SNAPSHOT, 'w') as handle:
        json.dump(tools, handle, ensure_ascii=False, indent=1)
        handle.write('\n')
    print('已写入 %d 个工具到 %s' % (len(tools), os.path.relpath(SNAPSHOT, ROOT)))


if __name__ == '__main__':
    main()
