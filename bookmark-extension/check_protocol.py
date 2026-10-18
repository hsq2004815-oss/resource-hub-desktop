#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抽屉书签桥 —— 协议自检（只使用 Python 标准库，不需要浏览器）。

本脚本做两件事：

1) 静态检查 manifest.json / background.js：
   端口范围 47821-47830、四个端点（/ping、/commands、/ack、/events）、
   1500ms 轮询间隔、事件批处理与缓存上限、权限声明等是否与 contract 一致。

2) 在 127.0.0.1:47821（被占用则依次尝试 47822-47830，全部被占用时改由系统分配端口）
   启动一个与后端 contract 完全一致的「模拟 bridge」，然后按 contract 走一遍：
   GET /ping -> GET /commands -> POST /ack -> POST /events -> OPTIONS 预检，
   并验证非法请求会被拒绝。这样 CI 无需启动浏览器即可校验通信协议。

用法：
    python check_protocol.py

输出：逐行 PASS / FAIL；全部通过时退出码为 0，否则为 1。
"""

from __future__ import annotations

import json
import re
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
BRIDGE_PORTS = range(47821, 47831)

# 与 background.js / 后端 contract 一致的固定响应。
PING_BODY = {"app": "resource-hub", "protocol": 1}
SAMPLE_COMMAND = {
    "id": "cmd-selfcheck-1",
    "op": "remove",
    "urls": ["https://example.com/old"],
    "createdAt": "2026-01-01T00:00:00Z",
}

# 自检结果计数（模块级全局，脚本很短，无需封装成类）。
PASSED = 0
FAILED = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    """记录并打印一条 PASS / FAIL。"""
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"PASS  {name}")
    else:
        FAILED += 1
        suffix = f"  ({detail})" if detail else ""
        print(f"FAIL  {name}{suffix}")


# ---------------------------------------------------------------------------
# 静态检查
# ---------------------------------------------------------------------------
def run_static_checks() -> None:
    print("[1/2] 静态检查 manifest.json / background.js")

    manifest_path = BASE_DIR / "manifest.json"
    background_path = BASE_DIR / "background.js"
    readme_path = BASE_DIR / "README.md"

    manifest = {}
    check("manifest.json 存在", manifest_path.is_file())
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            check("manifest.json 是合法 JSON 对象", isinstance(manifest, dict))
        except (OSError, ValueError) as exc:
            check("manifest.json 是合法 JSON 对象", False, str(exc))
    manifest = manifest if isinstance(manifest, dict) else {}

    check("manifest_version == 3", manifest.get("manifest_version") == 3)
    check("name == '抽屉书签桥'", manifest.get("name") == "抽屉书签桥")
    check("version == '1.1.0'", manifest.get("version") == "1.1.0")
    check(
        "description 非空",
        isinstance(manifest.get("description"), str) and bool(manifest.get("description")),
    )
    permissions = manifest.get("permissions") or []
    check("permissions 含 bookmarks", "bookmarks" in permissions)
    check("permissions 含 storage", "storage" in permissions)
    host_permissions = manifest.get("host_permissions") or []
    check(
        "host_permissions 含 http://127.0.0.1/*",
        "http://127.0.0.1/*" in host_permissions,
        f"host_permissions={host_permissions!r}",
    )
    background = manifest.get("background") or {}
    check(
        "background.service_worker == background.js",
        background.get("service_worker") == "background.js",
        f"background={background!r}",
    )
    action = manifest.get("action") or {}
    check(
        "action.default_title 非空",
        isinstance(action.get("default_title"), str) and bool(action.get("default_title")),
    )

    source = ""
    source_readable = False
    if background_path.is_file():
        try:
            source = background_path.read_text(encoding="utf-8")
            source_readable = True
        except OSError:
            source_readable = False
    check("background.js 存在", background_path.is_file())
    check("background.js 可读取", source_readable)
    check("background.js 非空", bool(source))

    def has(text: str, label: str) -> None:
        check(f"background.js 含 {label}", text in source)

    def has_pattern(pattern: str, label: str) -> None:
        check(f"background.js 含 {label}", re.search(pattern, source) is not None)

    has("127.0.0.1", "本机回环地址")
    has("http://", "HTTP 协议前缀")
    has_pattern(r"PORT_MIN\s*=\s*47821\b", "端口起点 47821")
    has_pattern(r"PORT_MAX\s*=\s*47830\b", "端口终点 47830")
    has("/ping", "ping 端点")
    has("/commands", "commands 端点")
    has("/ack", "ack 端点")
    has("/events", "events 端点")
    has_pattern(r"POLL_INTERVAL_MS\s*=\s*1500\b", "1500ms 轮询间隔")
    has("resource-hub", "app 标识")
    has("protocol", "protocol 字段")
    has("chrome.bookmarks.search", "书签搜索 API")
    has("chrome.bookmarks.remove", "书签删除 API")
    has("onRemoved", "书签删除监听")
    has("onChanged", "书签改名监听")
    has("chrome.storage.local", "端口/事件缓存")
    has_pattern(r"EVENT_BATCH_MS\s*=\s*400\b", "400ms 事件批处理窗口")
    has_pattern(r"MAX_PENDING_EVENTS\s*=\s*500\b", "500 条事件缓存上限")
    has("AbortController", "请求超时控制")
    has("onStartup", "浏览器启动恢复轮询")
    has("discoverPort", "端口发现逻辑")

    # 不允许拆分出额外文件依赖：service worker 必须是单文件原生 JS。
    has_dynamic_import = re.search(r"(?m)^\s*(?:import|export)\s", source) is not None
    has_require = re.search(r"\brequire\s*\(", source) is not None
    check("background.js 无第三方依赖（无 import/export/require）", not has_dynamic_import and not has_require)

    check("README.md 存在", readme_path.is_file())
    check(
        "check_protocol.py 与 manifest.json 同目录（可随扩展一起分发）",
        (BASE_DIR / "check_protocol.py").is_file(),
    )


# ---------------------------------------------------------------------------
# 模拟 bridge：与后端 contract 一致的 HTTP 服务
# ---------------------------------------------------------------------------
def _is_non_negative_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def validate_ack_payload(payload) -> str | None:
    """校验 POST /ack 请求体；返回错误描述，合法时返回 None。"""
    if not isinstance(payload, dict):
        return "请求体必须是 JSON 对象"
    results = payload.get("results")
    if not isinstance(results, list):
        return "results 必须是数组"
    for index, item in enumerate(results):
        if not isinstance(item, dict):
            return f"results[{index}] 必须是对象"
        if not isinstance(item.get("id"), str) or not item.get("id"):
            return f"results[{index}].id 必须是非空字符串"
        if not _is_non_negative_int(item.get("removed")):
            return f"results[{index}].removed 必须是非负整数"
        if not _is_non_negative_int(item.get("failed")):
            return f"results[{index}].failed 必须是非负整数"
    return None


def validate_events_payload(payload) -> str | None:
    """校验 POST /events 请求体；返回错误描述，合法时返回 None。"""
    if not isinstance(payload, dict):
        return "请求体必须是 JSON 对象"
    events = payload.get("events")
    if not isinstance(events, list):
        return "events 必须是数组"
    for index, item in enumerate(events):
        if not isinstance(item, dict):
            return f"events[{index}] 必须是对象"
        event_type = item.get("type")
        if event_type not in ("removed", "changed"):
            return f"events[{index}].type 必须是 removed 或 changed"
        if not isinstance(item.get("url"), str) or not item.get("url"):
            return f"events[{index}].url 必须是非空字符串"
        title = item.get("title")
        if "title" in item and not isinstance(title, str):
            return f"events[{index}].title 必须是字符串"
        if event_type == "changed" and not isinstance(title, str):
            return f"events[{index}].title 在 changed 事件中是必填字符串"
    return None


class BridgeState:
    """模拟 bridge 的内存状态（单次自检进程内使用）。"""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.commands: list[dict] = [dict(SAMPLE_COMMAND)]
        self.acks: list[dict] = []
        self.events: list[dict] = []


STATE = BridgeState()


class BridgeHandler(BaseHTTPRequestHandler):
    server_version = "ResourceHubMockBridge/1.0"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003 - 覆盖基类，保持安静
        pass

    # -- 响应工具 ---------------------------------------------------------
    def _send_json(self, status: int, payload) -> None:
        raw = b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        if raw:
            self.wfile.write(raw)

    def _send_no_content(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _read_json_body(self):
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            length = 0
        if length <= 0:
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    def _route(self) -> str:
        return self.path.split("?", 1)[0]

    # -- 路由 -------------------------------------------------------------
    def do_OPTIONS(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 约定
        self._send_no_content()

    def do_GET(self) -> None:  # noqa: N802
        route = self._route()
        if route == "/ping":
            self._send_json(200, dict(PING_BODY))
            return
        if route == "/commands":
            with STATE.lock:
                commands = list(STATE.commands)
                STATE.commands = []
            self._send_json(200, {"commands": commands})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        route = self._route()
        payload = self._read_json_body()
        if route == "/ack":
            error = validate_ack_payload(payload)
            if error:
                self._send_json(400, {"error": error})
                return
            with STATE.lock:
                STATE.acks.append(payload)
            self._send_json(200, {"ok": True})
            return
        if route == "/events":
            error = validate_events_payload(payload)
            if error:
                self._send_json(400, {"error": error})
                return
            with STATE.lock:
                STATE.events.append(payload)
            self._send_json(200, {"ok": True})
            return
        self._send_json(404, {"error": "not found"})


class BridgeServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address) -> None:  # noqa: D401
        # 自检过程中客户端断开等噪音不打印堆栈，避免干扰 PASS/FAIL 输出。
        pass


# ---------------------------------------------------------------------------
# HTTP 客户端
# ---------------------------------------------------------------------------
def http_call(method: str, url: str, payload=None, timeout: float = 3.0):
    """返回 (status, headers, parsed_json_or_None)，不抛异常。"""
    data = None
    headers: dict[str, str] = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.getcode()
            response_headers = response.headers
            raw = response.read()
    except urllib.error.HTTPError as error:
        status = error.code
        response_headers = error.headers
        raw = error.read()
    except OSError as error:
        return 0, {}, None
    parsed = None
    if raw:
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            parsed = None
    return status, response_headers, parsed


# ---------------------------------------------------------------------------
# 动态检查
# ---------------------------------------------------------------------------
def run_dynamic_checks(base_url: str) -> None:
    print("\n[2/2] 动态检查：用模拟 bridge 走一遍 contract")

    # /ping -----------------------------------------------------------------
    status, headers, body = http_call("GET", f"{base_url}/ping")
    check("bridge GET /ping 返回 200", status == 200, f"status={status}")
    check(
        "bridge /ping 响应为 {'app':'resource-hub','protocol':1}",
        body == PING_BODY,
        f"body={body!r}",
    )
    check(
        "bridge 响应带 CORS 头 Access-Control-Allow-Origin: *",
        headers.get("Access-Control-Allow-Origin") == "*",
    )

    # /commands -------------------------------------------------------------
    status, _, body = http_call("GET", f"{base_url}/commands")
    commands = body.get("commands") if isinstance(body, dict) else None
    check(
        "bridge GET /commands 返回 200 且 commands 为数组",
        status == 200 and isinstance(commands, list),
        f"status={status}, body={body!r}",
    )
    first = commands[0] if isinstance(commands, list) and commands else None
    command_ok = (
        isinstance(first, dict)
        and isinstance(first.get("id"), str)
        and bool(first.get("id"))
        and first.get("op") == "remove"
        and isinstance(first.get("urls"), list)
        and all(isinstance(url, str) for url in first.get("urls") or [])
        and isinstance(first.get("createdAt"), str)
    )
    check(
        "commands[0] 符合 {id, op:'remove', urls, createdAt} 形状",
        command_ok,
        f"command={first!r}",
    )

    status, _, body = http_call("GET", f"{base_url}/commands")
    check(
        "GET /commands 第二次拉取为空（命令已投递并出队）",
        status == 200 and isinstance(body, dict) and body.get("commands") == [],
        f"body={body!r}",
    )

    # /ack ------------------------------------------------------------------
    status, _, body = http_call(
        "POST",
        f"{base_url}/ack",
        {"results": [{"id": "cmd-selfcheck-1", "removed": 2, "failed": 0}]},
    )
    check(
        "POST /ack 接受合法回执（200 + ok）",
        status == 200 and isinstance(body, dict) and body.get("ok") is True,
        f"status={status}, body={body!r}",
    )
    status, _, _ = http_call("POST", f"{base_url}/ack", {"results": [{"id": "only-id"}]})
    check("POST /ack 拒绝缺 removed/failed 的回执（400）", status == 400, f"status={status}")

    # /events ---------------------------------------------------------------
    sample_events = [
        {"type": "removed", "url": "https://example.com/old"},
        {"type": "changed", "url": "https://example.com/new", "title": "新标题"},
    ]
    status, _, body = http_call("POST", f"{base_url}/events", {"events": sample_events})
    check(
        "POST /events 接受合法事件（200 + ok）",
        status == 200 and isinstance(body, dict) and body.get("ok") is True,
        f"status={status}, body={body!r}",
    )
    status, _, _ = http_call(
        "POST",
        f"{base_url}/events",
        {"events": [{"type": "unknown", "url": ""}]},
    )
    check("POST /events 拒绝非法事件（400）", status == 400, f"status={status}")

    # OPTIONS 预检 ----------------------------------------------------------
    status, headers, _ = http_call("OPTIONS", f"{base_url}/ping")
    check(
        "OPTIONS 预检返回 204 且带 CORS 头",
        status == 204 and headers.get("Access-Control-Allow-Origin") == "*",
        f"status={status}",
    )

    # 模拟 bridge 是否真的收到了我们的回执/事件 --------------------------------
    with STATE.lock:
        ack_batches = len(STATE.acks)
        event_batches = len(STATE.events)
    check("模拟 bridge 收到 1 批 ack", ack_batches == 1, f"ack_batches={ack_batches}")
    check("模拟 bridge 收到 1 批 events", event_batches == 1, f"event_batches={event_batches}")


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def start_bridge():
    """在 47821-47830 中找第一个空闲端口启动模拟 bridge；全忙时交给系统分配。"""
    for port in BRIDGE_PORTS:
        try:
            server = BridgeServer(("127.0.0.1", port), BridgeHandler)
            return server, port, None
        except OSError:
            continue
    server = BridgeServer(("127.0.0.1", 0), BridgeHandler)
    return server, server.server_address[1], "47821-47830 均被占用，已改用系统分配的端口"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass

    print("抽屉书签桥 —— 协议自检 (check_protocol.py)")
    print(f"扩展目录: {BASE_DIR}")

    run_static_checks()

    server = None
    try:
        server, port, fallback_note = start_bridge()
        if fallback_note:
            print(f"WARN  模拟 bridge: {fallback_note}")
        else:
            print(f"INFO  模拟 bridge 监听 127.0.0.1:{port}")
        check("模拟 bridge 已启动", server is not None)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        run_dynamic_checks(f"http://127.0.0.1:{port}")
    except OSError as exc:
        check("模拟 bridge 已启动", False, str(exc))
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()

    print()
    print(f"SUMMARY: {PASSED} PASS, {FAILED} FAIL")
    if FAILED == 0:
        print("RESULT: PASS —— 扩展与后端 contract 一致（未启动浏览器）")
        return 0
    print("RESULT: FAIL —— 请根据上面 FAIL 行修正")
    return 1


if __name__ == "__main__":
    sys.exit(main())
