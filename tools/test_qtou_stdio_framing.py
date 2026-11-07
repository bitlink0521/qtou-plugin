#!/usr/bin/env python3
"""Content-Length is a byte count. Isolated stdio regressions, no network and no credentials."""
import json
import os
import select
import subprocess
import sys
import tempfile
import threading
import unittest

PROXY = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'qtou_mcp_proxy.py')
LOCAL_NAMES = [
    'qtou_account_list', 'qtou_account_add', 'qtou_account_switch', 'qtou_account_logout',
]
MARKER = '密码qtpat_NOT_A_REAL_TOKEN'


def listed_names():
    catalog_path = os.path.join(os.path.dirname(PROXY), 'qtou_tool_catalog.json')
    catalog = json.load(open(catalog_path, encoding='utf-8'))
    return [tool['name'] for tool in catalog['tools']] + LOCAL_NAMES


def frame(message):
    raw = json.dumps(message, ensure_ascii=False).encode('utf-8')
    return ('Content-Length: %d\r\n\r\n' % len(raw)).encode('ascii') + raw


def spawn(home, encoding='utf-8'):
    env = {
        'HOME': home,
        'PATH': '/usr/bin:/bin',
        'PYTHONPATH': os.path.dirname(PROXY),
        'PYTHONUNBUFFERED': '1',
        'PYTHONIOENCODING': encoding,
        'LC_ALL': 'C.UTF-8' if encoding.lower() == 'utf-8' else 'C',
        'NO_PROXY': '*',
        'QTOU_MCP_URL': 'http://127.0.0.1:9/api/v1/agent/mcp',
        'QTOU_LOGIN_URL': 'http://127.0.0.1:9/api/v1/agent/auth/login',
    }
    proc = subprocess.Popen(
        [sys.executable, '-u', PROXY],
        cwd=os.path.dirname(PROXY),
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stderr = []

    def drain():
        for line in iter(proc.stderr.readline, b''):
            stderr.append(line.decode('utf-8', 'replace').rstrip('\n'))

    threading.Thread(target=drain, daemon=True).start()
    return proc, stderr


def read_line(fd, deadline):
    import time
    buf = bytearray()
    while time.time() < deadline:
        ready, _, _ = select.select([fd], [], [], max(0, deadline - time.time()))
        if not ready:
            return None
        chunk = os.read(fd, 1)
        if not chunk:
            return bytes(buf)
        buf.extend(chunk)
        if chunk == b'\n':
            return bytes(buf)
    return None


def read_exact(fd, size, deadline):
    import time
    buf = bytearray()
    while len(buf) < size:
        if time.time() >= deadline:
            return None
        ready, _, _ = select.select([fd], [], [], max(0, deadline - time.time()))
        if not ready:
            return None
        chunk = os.read(fd, size - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


def read_frame(fd, timeout):
    import time
    deadline = time.time() + timeout
    length = None
    while True:
        line = read_line(fd, deadline)
        if line is None:
            return {'kind': 'timeout'}
        if line == b'':
            return {'kind': 'eof'}
        if line in (b'\n', b'\r\n'):
            break
        if line.lower().startswith(b'content-length:'):
            length = int(line.split(b':', 1)[1].strip())
    if length is None:
        return {'kind': 'no-length'}
    body = read_exact(fd, length, deadline)
    if body is None or len(body) != length:
        return {'kind': 'short'}
    return {'kind': 'frame', 'message': json.loads(body.decode('utf-8'))}


def stop(proc):
    if proc.poll() is None:
        proc.kill()
    proc.wait(timeout=5)


class FramingTests(unittest.TestCase):
    def exchange(self, blob, expect, timeout=4):
        home = tempfile.mkdtemp(prefix='qtou-frame-')
        proc, stderr = spawn(home)
        try:
            proc.stdin.write(blob)
            proc.stdin.flush()
            frames = [read_frame(proc.stdout.fileno(), timeout) for _ in range(expect)]
            return frames, stderr
        finally:
            stop(proc)

    def test_chinese_back_to_back_frames_keep_their_ids(self):
        first = frame({
            'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
            'params': {'protocolVersion': '2024-11-05', 'capabilities': {},
                       'clientInfo': {'name': '客户端', 'version': '0'}},
        })
        second = frame({
            'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list',
            'params': {'note': '中文连帧'},
        })
        frames, stderr = self.exchange(first + second, 2)
        self.assertEqual(frames[0]['message']['id'], 1)
        self.assertEqual(frames[0]['message']['result']['serverInfo']['name'], 'qtou-agent-mcp')
        tools = frames[1]['message']['result']['tools']
        self.assertEqual([item['name'] for item in tools], listed_names())
        self.assertFalse(any('ignored a non-JSON' in line for line in stderr))
        self.assertNotIn('中文连帧', '\n'.join(stderr))
        self.assertNotIn('客户端', '\n'.join(stderr))

    def test_chinese_reply_length_is_bytes_when_stdout_encoding_is_ascii(self):
        blob = frame({'jsonrpc': '2.0', 'id': 6, 'method': 'tools/list', 'params': {'note': '中文长度'}})
        home = tempfile.mkdtemp(prefix='qtou-ascii-')
        proc, stderr = spawn(home, encoding='ascii')
        try:
            proc.stdin.write(blob)
            proc.stdin.flush()
            message = read_frame(proc.stdout.fileno(), 4)
        finally:
            stop(proc)
        self.assertEqual(message.get('kind'), 'frame', stderr)
        self.assertEqual(message['message']['id'], 6)
        tools = message['message']['result']['tools']
        self.assertEqual([item['name'] for item in tools], listed_names())
        self.assertTrue(any(any(ord(char) > 127 for char in item.get('description', '')) for item in tools))

    def test_ascii_frame_still_returns_local_tools(self):
        blob = frame({'jsonrpc': '2.0', 'id': 7, 'method': 'tools/list', 'params': {}})
        frames, stderr = self.exchange(blob, 1)
        self.assertEqual(frames[0]['message']['id'], 7)
        self.assertEqual([item['name'] for item in frames[0]['message']['result']['tools']], listed_names())
        self.assertEqual(stderr, [])

    def test_ndjson_ascii_and_chinese_lines_still_work(self):
        lines = ''.join(json.dumps(message, ensure_ascii=False) + '\n' for message in (
            {'jsonrpc': '2.0', 'id': 3, 'method': 'initialize',
             'params': {'protocolVersion': '2024-11-05', 'capabilities': {},
                        'clientInfo': {'name': 'ndjson', 'version': '0'}}},
            {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/list', 'params': {'note': '行内中文'}},
        )).encode('utf-8')
        home = tempfile.mkdtemp(prefix='qtou-ndjson-')
        proc, stderr = spawn(home)
        try:
            proc.stdin.write(lines)
            proc.stdin.flush()
            first = proc.stdout.readline()
            second = proc.stdout.readline()
        finally:
            stop(proc)
        self.assertEqual(json.loads(first.decode('utf-8'))['id'], 3)
        listed = json.loads(second.decode('utf-8'))
        self.assertEqual(listed['id'], 4)
        self.assertEqual([item['name'] for item in listed['result']['tools']], listed_names())
        self.assertNotIn('行内中文', '\n'.join(stderr))

    def test_truncated_frame_is_not_parsed_and_marker_stays_off_stderr(self):
        blob = b'Content-Length: 200\r\n\r\n' + MARKER.encode('utf-8')
        home = tempfile.mkdtemp(prefix='qtou-short-')
        proc, stderr = spawn(home)
        try:
            proc.stdin.write(blob)
            proc.stdin.close()
            proc.wait(timeout=5)
            stdout = proc.stdout.read()
        finally:
            if proc.poll() is None:
                stop(proc)
        text = '\n'.join(stderr)
        self.assertIn('ignored a short framed body', text)
        self.assertNotIn(MARKER, text)
        self.assertNotIn('密码', text)
        self.assertNotIn('qtpat_', text)
        self.assertEqual(stdout, b'')

    def test_good_frame_then_truncated_frame_keeps_only_the_first_response(self):
        # tools/list is answered on a daemon thread. Closing stdin on a following
        # short frame can exit the process before that reply is written. Read the
        # completed frame first. The short frame is not a parsed message.
        good = frame({'jsonrpc': '2.0', 'id': 8, 'method': 'tools/list', 'params': {}})
        home = tempfile.mkdtemp(prefix='qtou-short2-')
        proc, stderr = spawn(home)
        try:
            proc.stdin.write(good)
            proc.stdin.flush()
            message = read_frame(proc.stdout.fileno(), 4)
            self.assertEqual(message.get('kind'), 'frame', message)
            self.assertEqual(message['message'].get('id'), 8)
            self.assertIn('result', message['message'])
            proc.stdin.write(b'Content-Length: 80\r\n\r\n' + MARKER.encode('utf-8'))
            proc.stdin.close()
            extra = read_frame(proc.stdout.fileno(), 2)
            proc.wait(timeout=5)
        finally:
            if proc.poll() is None:
                stop(proc)
        self.assertIn(extra.get('kind'), ('eof', 'timeout', 'short'))
        self.assertNotIn('message', extra)
        text = '\n'.join(stderr)
        self.assertIn('ignored a short framed body', text)
        self.assertNotIn(MARKER, text)

    def test_bad_and_negative_length_do_not_swallow_the_following_ndjson_line(self):
        line = (json.dumps({'jsonrpc': '2.0', 'id': 9, 'method': 'tools/list', 'params': {}}) + '\n').encode('utf-8')
        for prefix in (b'Content-Length: nope\r\n\r\n', b'Content-Length: -1\r\n\r\n'):
            home = tempfile.mkdtemp(prefix='qtou-badlen-')
            proc, stderr = spawn(home)
            try:
                proc.stdin.write(prefix + line)
                proc.stdin.flush()
                raw = proc.stdout.readline()
            finally:
                stop(proc)
            self.assertTrue(raw, stderr)
            self.assertEqual(json.loads(raw.decode('utf-8'))['id'], 9)
            self.assertTrue(any('bad Content-Length header' in item for item in stderr))


if __name__ == '__main__':
    unittest.main()
