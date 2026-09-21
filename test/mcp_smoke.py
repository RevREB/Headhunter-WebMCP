#!/usr/bin/env python3
"""End-to-end smoke test against a running Headhunter-WebMCP container.

What this proves (the claims the README makes, in order):
  1. the MCP endpoint speaks MCP -- a real initialize handshake, not a 200 OK;
  2. it advertises the tools Core drives it with (navigate + screenshot);
  3. headed Chromium actually launches on the Xvfb display and renders a page:
     we navigate to a fixture served from the CI host and require the marker
     string back out of the accessibility snapshot;
  4. a screenshot comes back as real image bytes -- the one control the README
     says catches silently-empty submits, and the one thing a no-render engine
     cannot fake;
  5. noVNC serves its client page, so the human take-over path exists.

Stdlib only, so it runs on a bare runner with no pip install.
"""

import argparse
import base64
import json
import sys
import time
import urllib.error
import urllib.request

PROTOCOL_VERSION = "2025-06-18"
CANDIDATE_PATHS = ("/mcp", "/", "/sse")
REQUIRED_TOOLS = ("browser_navigate", "browser_take_screenshot")

failures = []


def ok(msg):
    print(f"  PASS  {msg}", flush=True)


def fail(msg, detail=""):
    failures.append(msg)
    print(f"  FAIL  {msg}", flush=True)
    if detail:
        print(f"        {detail[:2000]}", flush=True)


def parse_body(raw, content_type):
    """A streamable-HTTP server may answer with application/json or with an SSE
    frame; accept either and return the first JSON-RPC message."""
    raw = raw.strip()
    if not raw:
        return None
    if "text/event-stream" in content_type:
        for line in raw.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        return None
    return json.loads(raw)


class MCPClient:
    def __init__(self, url):
        self.url = url
        self.session_id = None

    def post(self, payload, timeout=60):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = urllib.request.Request(
            self.url, data=json.dumps(payload).encode(), headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            sid = resp.headers.get("mcp-session-id")
            if sid:
                self.session_id = sid
            return parse_body(
                resp.read().decode("utf-8", "replace"),
                resp.headers.get("Content-Type", ""),
            )

    def call(self, method, params=None, msg_id=1, timeout=60):
        payload = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params is not None:
            payload["params"] = params
        res = self.post(payload, timeout=timeout)
        if res is None:
            raise RuntimeError(f"{method}: empty response")
        if "error" in res:
            raise RuntimeError(f"{method}: {json.dumps(res['error'])[:500]}")
        return res.get("result", {})

    def notify(self, method, params=None):
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        try:
            self.post(payload, timeout=30)
        except urllib.error.HTTPError as exc:  # 202 with no body is normal
            if exc.code >= 400:
                raise


def connect(base, deadline):
    """Find the streamable-HTTP path and complete the handshake."""
    last = ""
    while time.time() < deadline:
        for path in CANDIDATE_PATHS:
            client = MCPClient(base.rstrip("/") + path)
            try:
                result = client.call(
                    "initialize",
                    {
                        "protocolVersion": PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": "webmcp-ci-smoke", "version": "1"},
                    },
                    timeout=20,
                )
            except Exception as exc:  # noqa: BLE001 - server may not be up yet
                last = f"{path}: {type(exc).__name__}: {exc}"
                continue
            client.notify("notifications/initialized")
            return client, result
        time.sleep(2)
    raise SystemExit(f"could not complete an MCP initialize on {base} ({last})")


def texts(result):
    """Flatten every text block of a tools/call result."""
    return "\n".join(
        c.get("text", "")
        for c in result.get("content", [])
        if c.get("type") == "text"
    )


def images(result):
    return [c for c in result.get("content", []) if c.get("type") == "image"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mcp-base", default="http://127.0.0.1:8931")
    ap.add_argument("--vnc-base", default="http://127.0.0.1:6080")
    ap.add_argument("--page-url", required=True)
    ap.add_argument("--marker", default="WEBMCP-SMOKE-MARKER-9f31")
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()

    print("== MCP handshake ==", flush=True)
    client, init = connect(args.mcp_base, time.time() + args.timeout)
    server = init.get("serverInfo", {})
    print(f"  endpoint {client.url}  server {json.dumps(server)}", flush=True)
    if init.get("protocolVersion"):
        ok(f"initialize negotiated protocol {init['protocolVersion']}")
    else:
        fail("initialize returned no protocolVersion", json.dumps(init))
    if "playwright" in json.dumps(server).lower():
        ok("server identifies as @playwright/mcp")
    else:
        fail("serverInfo is not @playwright/mcp", json.dumps(server))

    print("== tool contract ==", flush=True)
    tools = {t["name"] for t in client.call("tools/list", {}, msg_id=2).get("tools", [])}
    print(f"  {len(tools)} tools advertised", flush=True)
    for name in REQUIRED_TOOLS:
        if name in tools:
            ok(f"tool {name} advertised")
        else:
            fail(f"tool {name} missing", ", ".join(sorted(tools)))
    if all(name in tools for name in REQUIRED_TOOLS):
        print("== headed chromium renders a page ==", flush=True)
        try:
            nav = client.call(
                "tools/call",
                {"name": "browser_navigate", "arguments": {"url": args.page_url}},
                msg_id=3,
                timeout=args.timeout,
            )
            body = texts(nav)
            if nav.get("isError"):
                fail("browser_navigate returned isError", body)
            if args.marker not in body and "browser_snapshot" in tools:
                body = texts(
                    client.call(
                        "tools/call",
                        {"name": "browser_snapshot", "arguments": {}},
                        msg_id=4,
                        timeout=args.timeout,
                    )
                )
            if args.marker in body:
                ok(f"page rendered: snapshot contains {args.marker}")
            else:
                fail("marker absent from page snapshot", body)
        except Exception as exc:  # noqa: BLE001
            fail("browser_navigate raised", f"{type(exc).__name__}: {exc}")

        print("== screenshot ==", flush=True)
        try:
            shot = client.call(
                "tools/call",
                {"name": "browser_take_screenshot", "arguments": {}},
                msg_id=5,
                timeout=args.timeout,
            )
            imgs = images(shot)
            if not imgs:
                fail("screenshot returned no image content", texts(shot))
            else:
                raw = base64.b64decode(imgs[0].get("data", ""), validate=False)
                if len(raw) < 2000:
                    fail(f"screenshot is only {len(raw)} bytes", "")
                elif raw[:3] == b"\xff\xd8\xff" or raw[:8] == b"\x89PNG\r\n\x1a\n":
                    ok(f"screenshot is {len(raw)} bytes of real {imgs[0].get('mimeType')}")
                else:
                    fail("screenshot bytes are not JPEG or PNG", repr(raw[:16]))
        except Exception as exc:  # noqa: BLE001
            fail("browser_take_screenshot raised", f"{type(exc).__name__}: {exc}")

    print("== noVNC take-over path ==", flush=True)
    url = args.vnc_base.rstrip("/") + "/vnc.html"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            page = resp.read().decode("utf-8", "replace")
        if resp.status == 200 and "noVNC" in page:
            ok("noVNC serves vnc.html")
        else:
            fail(f"vnc.html status={resp.status}", page[:300])
    except Exception as exc:  # noqa: BLE001
        fail("noVNC unreachable", f"{type(exc).__name__}: {exc}")

    print(flush=True)
    if failures:
        print(f"SMOKE FAILED ({len(failures)}): " + "; ".join(failures), flush=True)
        return 1
    print("SMOKE PASSED", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
