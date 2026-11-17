#!/usr/bin/env python3
"""SSH-only, loopback-only, authenticated read-only preview of AI Arena.

Serves a PREVIOUSLY TESTED React build from the isolated /tmp checkout.
Forwards only GET for the three V3 Brain display endpoints and auth status,
and POST for password login. All trading/configuration writes are denied.
The phone reaches it via Termius LOCAL SSH port forwarding (not public IP).
Does not modify production, proxies, firewalls, workers or journal files.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
import hashlib
import json
import mimetypes
import os
import socket
import subprocess
import sys

PORT = 18088
BACKEND = "http://127.0.0.1:8002"
EXPECTED_SOURCE = "a9e35fb08460327faf8789df9f9631c547c07371"
EXPECTED_BUNDLE = "e222e6ca6bf61406d38d08cda9e4dcd22ca4c3990f167b56106bca486064fd3e"
ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "frontend" / "build"
READ_API = frozenset((
    "/api/v3/overview",
    "/api/v3/brain/status",
    "/api/v3/brain/trades",
    "/api/auth/password-status",
    "/api/auth/webauthn/status",
))
LOGIN = "/api/auth/login"
MAX_LOGIN_BYTES = 8192
MAX_API_REPLY = 3_000_000
MAX_FILE_BYTES = 5_000_000


def refuse(reason):
    print("ARENA_PREVIEW RESULT=REFUSED_" + reason, flush=True)
    raise SystemExit(2)


def git(*args):
    return subprocess.run(
        ("git", "-C", str(ROOT), *args), capture_output=True, text=True,
        timeout=8, check=False,
    )


def preflight():
    if not str(ROOT).startswith("/tmp/arena-ui-smoke.") or ROOT.name != "repo":
        refuse("NOT_IN_ISOLATED_TMP_CHECKOUT")
    branch = git("branch", "--show-current")
    if branch.returncode or branch.stdout.strip() != "work/arena-ui-smoke-build-20261117":
        refuse("WRONG_BRANCH")
    result = git("rev-parse", "HEAD")
    if result.returncode:
        refuse("GIT_HEAD_UNAVAILABLE")
    if git("diff", "--quiet", EXPECTED_SOURCE, result.stdout.strip(), "--", "frontend").returncode:
        refuse("FRONTEND_CHANGED_SINCE_VERIFIED_BUILD")
    # CRA has regenerated frontend/build from the validated source. Some
    # historical build artifacts are tracked in Git, so git status must not
    # reject those generated differences. Every OTHER file remains guarded.
    # The new bundle is independently pinned by EXPECTED_BUNDLE below.
    status = git("status", "--porcelain", "--untracked-files=normal",
                 "--", ".", ":(exclude)frontend/build")
    if status.returncode:
        refuse("GIT_STATUS_UNAVAILABLE")
    if status.stdout.strip():
        refuse("DIRTY_SOURCE_CHECKOUT")
    js = STATIC / "static/js/main.a48d3857.js"
    # Do not trust a guessed bundle name if the fingerprint differs.
    bundles = list((STATIC / "static/js").glob("main.*.js"))
    if len(bundles) != 1 or not bundles[0].is_file():
        refuse("COMPILED_BUNDLE_MISSING")
    if (hashlib.sha256(bundles[0].read_bytes()).hexdigest()
            != EXPECTED_BUNDLE):
        refuse("COMPILED_BUNDLE_SHA_MISMATCH")
    if not (STATIC / "index.html").is_file():
        refuse("INDEX_MISSING")
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=0.8):
            refuse("PREVIEW_PORT_IN_USE")
    except OSError:
        pass
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(BACKEND + "/api/health", timeout=4) as r:
            if r.status != 200:
                refuse("BACKEND_HEALTH_NOT_OK")
            r.read(4000)
    except (HTTPError, URLError, OSError, TimeoutError):
        refuse("BACKEND_LOCALHOST_HEALTH_UNAVAILABLE")
    print("ARENA_PREVIEW mode=SSH_ONLY_READ_ONLY", flush=True)
    print("ARENA_PREVIEW frontend_sha256=" + EXPECTED_BUNDLE, flush=True)
    print("ARENA_PREVIEW listening_only_on=127.0.0.1:" + str(PORT), flush=True)
    print("ARENA_PREVIEW backend_healthy=" + BACKEND, flush=True)
    print("ARENA_PREVIEW allowed_api=V3_BRAIN_GETS_AND_PASSWORD_LOGIN_ONLY", flush=True)
    print("ARENA_PREVIEW production_changed=0 service_changes=0 orders=0", flush=True)
    return True


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = build_opener(ProxyHandler({}), NoRedirect())


class Preview(BaseHTTPRequestHandler):
    server_version = "ArenaReadOnlyPreview"
    sys_version = ""

    def log_message(self, fmt, *args):
        # No request paths, Authorization tokens or login passwords in logs.
        return

    def headers_common(self, code, content_type, length):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store, private")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()

    def fail(self, code, note):
        data = json.dumps({"detail": note}).encode("utf-8")
        self.headers_common(code, "application/json; charset=utf-8", len(data))
        if self.command != "HEAD":
            self.wfile.write(data)

    def host_ok(self):
        return self.headers.get("Host") in (
            f"127.0.0.1:{PORT}", f"localhost:{PORT}",
        ) and self.client_address[0] in ("127.0.0.1", "::1")

    def do_GET(self):
        if not self.host_ok():
            return self.fail(403, "ONLY_LOCALHOST_SSH")
        target = urlsplit(self.path)
        if target.path.startswith("/api/"):
            return self.forward_api(target, None)
        if target.path == "/":
            self.send_response(302)
            self.send_header("Location", "/arena")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if target.path in ("/service-worker.js", "/sw.js"):
            return self.fail(404, "SERVICE_WORKER_DISABLED")
        safe = unquote(target.path)
        if "\x00" in safe or "\\" in safe:
            return self.fail(404, "BAD_STATIC_PATH")
        path = (STATIC / safe.lstrip("/")).resolve()
        if not path.is_relative_to(STATIC.resolve()):
            return self.fail(404, "BAD_STATIC_PATH")
        if path.is_file():
            if path.stat().st_size > MAX_FILE_BYTES:
                return self.fail(413, "STATIC_FILE_TOO_LARGE")
            data = path.read_bytes()
            media = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        elif not safe.rsplit("/", 1)[-1].count("."):
            data = (STATIC / "index.html").read_bytes()
            media = "text/html"
        else:
            return self.fail(404, "FILE_NOT_FOUND")
        self.headers_common(200, media, len(data))
        self.wfile.write(data)

    def do_POST(self):
        if not self.host_ok():
            return self.fail(403, "ONLY_LOCALHOST_SSH")
        target = urlsplit(self.path)
        if target.path != LOGIN or target.query:
            return self.fail(403, "TRADING_AND_MUTATIONS_DISABLED")
        raw_len = self.headers.get("Content-Length", "")
        if not raw_len.isascii() or not raw_len.isdecimal():
            return self.fail(411, "LOGIN_BODY_SIZE_REQUIRED")
        n = int(raw_len)
        if n < 2 or n > MAX_LOGIN_BYTES:
            return self.fail(413, "LOGIN_BODY_SIZE_INVALID")
        body = self.rfile.read(n)
        return self.forward_api(target, body)

    def do_PUT(self):
        return self.fail(403, "TRADING_AND_MUTATIONS_DISABLED")

    def do_DELETE(self):
        return self.fail(403, "TRADING_AND_MUTATIONS_DISABLED")

    def do_PATCH(self):
        return self.fail(403, "TRADING_AND_MUTATIONS_DISABLED")

    def forward_api(self, target, body):
        if body is None and (self.command != "GET" or target.path not in READ_API):
            return self.fail(403, "TRADING_AND_MUTATIONS_DISABLED")
        if target.path != "/api/v3/brain/trades" and target.query:
            return self.fail(400, "API_QUERY_NOT_ALLOWED")
        if target.path == "/api/v3/brain/trades" and target.query != "limit=100":
            return self.fail(400, "API_TRADES_LIMIT_MISMATCH")
        headers = {"Accept": "application/json"}
        token = self.headers.get("Authorization")
        if token and token.startswith("Bearer ") and len(token) < 5000:
            headers["Authorization"] = token
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = Request(BACKEND + target.path + (("?" + target.query) if target.query else ""),
                      headers=headers, data=body,
                      method="GET" if body is None else "POST")
        try:
            reply = OPENER.open(req, timeout=9)
        except HTTPError as err:
            reply = err
        except (URLError, OSError, TimeoutError):
            return self.fail(502, "BACKEND_READ_UNAVAILABLE")
        try:
            with reply:
                data = reply.read(MAX_API_REPLY + 1)
                if len(data) > MAX_API_REPLY:
                    return self.fail(502, "API_RESPONSE_TOO_LARGE")
                media = reply.headers.get("Content-Type", "application/json")
                if not media.startswith("application/json"):
                    return self.fail(502, "API_UNEXPECTED_CONTENT_TYPE")
                self.headers_common(reply.status, media, len(data))
                self.wfile.write(data)
        except (OSError, ConnectionError):
            return


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("--preflight", "--serve-ssh-only"):
        refuse("MODE_REQUIRED")
    preflight()
    if sys.argv[1] == "--preflight":
        print("ARENA_PREVIEW RESULT=READY_NOT_STARTED_NO_DEPLOY", flush=True)
        return
    print("ARENA_PREVIEW RESULT=SERVING_SSH_ONLY_NO_PRODUCTION_DEPLOY", flush=True)
    print("ARENA_PREVIEW phone_url_after_termius_forward=http://127.0.0.1:18088/arena", flush=True)
    with ThreadingHTTPServer(("127.0.0.1", PORT), Preview) as server:
        server.daemon_threads = True
        server.serve_forever(poll_interval=0.3)


if __name__ == "__main__":
    main()
