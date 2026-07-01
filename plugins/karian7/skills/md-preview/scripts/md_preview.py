#!/usr/bin/env python3
"""Preview a Markdown file in a browser with live reload."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlparse

SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = SKILL_DIR / "assets"
STATE_FILE = Path(tempfile.gettempdir()) / "md-preview-state.json"
LOG_FILE = Path(tempfile.gettempdir()) / "md-preview.log"
DEFAULT_PORT = 8000
DEFAULT_POLL_INTERVAL = 0.75
DEFAULT_BIND_HOST = "127.0.0.1"
VERSION_PATH = "/__md_preview/version"
UNLOAD_PATH = "/__md_preview/unload"
MAX_LOG_BYTES = 2 * 1024 * 1024  # 2 MB
# Auto-close watchdog thresholds (seconds)
AUTO_CLOSE_POLL_TIMEOUT = 10.0   # after unload beacon: no poll for this long → shutdown
AUTO_CLOSE_IDLE_TIMEOUT = 30.0   # without beacon: fallback idle timeout
AUTO_CLOSE_INITIAL_DELAY = 5.0   # grace period before watchdog activates


class ReusableHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def extract_title(markdown_path: Path) -> str:
    pattern = re.compile(r"^#\s+(.+)")
    for line in read_text(markdown_path).splitlines():
        match = pattern.match(line.strip())
        if match:
            return match.group(1).strip()
    return markdown_path.stem


def preview_name_for(markdown_path: Path) -> str:
    return f".{markdown_path.stem}.preview.html"


def preview_path_for(markdown_path: Path) -> Path:
    return markdown_path.with_name(preview_name_for(markdown_path))


def ensure_pandoc() -> None:
    if shutil.which("pandoc"):
        return
    raise RuntimeError("pandoc not found. Install it first, for example: brew install pandoc")


def resolve_markdown_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Markdown file not found: {path}")
    if not path.is_file():
        raise IsADirectoryError(f"Expected a file, got directory: {path}")
    return path


def inject_assets(preview_path: Path, source_path: Path) -> None:
    preview_html = read_text(preview_path)
    preview_css = read_text(ASSETS_DIR / "preview.css")
    reload_js = read_text(ASSETS_DIR / "preview_reload.js")
    source_name = html.escape(source_path.name)

    style_block = (
        '<meta http-equiv="Cache-Control" content="no-store" />\n'
        '<meta name="robots" content="noindex" />\n'
        f"<style>\n{preview_css}\n</style>\n"
    )
    script_block = (
        '<script>\n'
        f'window.__MD_PREVIEW_VERSION_URL = "{VERSION_PATH}";\n'
        f"{reload_js}\n"
        "</script>\n"
    )
    banner = (
        '<div class="md-preview-banner">'
        '<span class="md-preview-eyebrow">&#9741;</span>'
        f"<code>{source_name}</code>"
        "</div>\n"
        '<div id="md-preview-container">\n'
        '<div class="md-preview-body">\n'
    )
    banner_close = "</div>\n</div>\n"

    if "</head>" in preview_html:
        preview_html = preview_html.replace("</head>", f"{style_block}</head>", 1)
    else:
        preview_html = f"{style_block}{preview_html}"

    body_open_pattern = re.compile(r"<body([^>]*)>")
    preview_html, replacements = body_open_pattern.subn(
        lambda match: f"<body{match.group(1)}>\n{banner}", preview_html, count=1
    )
    if replacements == 0:
        preview_html = f"{banner}{preview_html}"

    if "</body>" in preview_html:
        preview_html = preview_html.replace("</body>", f"{banner_close}{script_block}</body>", 1)
    else:
        preview_html = f"{preview_html}\n{banner_close}\n{script_block}"

    write_text(preview_path, preview_html)


def build_preview(markdown_path: Path) -> Path:
    ensure_pandoc()
    preview_path = preview_path_for(markdown_path)
    title = extract_title(markdown_path)
    command = [
        "pandoc",
        str(markdown_path),
        "--from",
        "gfm",
        "--to",
        "html5",
        "--standalone",
        "--syntax-highlighting",
        "tango",
        f"--metadata=title:{title}",
        "--output",
        str(preview_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "pandoc failed"
        raise RuntimeError(message)
    inject_assets(preview_path, markdown_path)
    return preview_path


def process_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def load_state() -> dict[str, Any] | None:
    if not STATE_FILE.exists():
        return None
    try:
        return json.loads(read_text(STATE_FILE))
    except json.JSONDecodeError:
        return None


def write_state(state: dict[str, Any]) -> None:
    write_text(STATE_FILE, json.dumps(state, ensure_ascii=False, indent=2))


def remove_state_if_owned(pid: int) -> None:
    state = load_state()
    if state and state.get("pid") == pid and STATE_FILE.exists():
        STATE_FILE.unlink()


def port_is_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((DEFAULT_BIND_HOST, port)) == 0


def find_free_port(start_port: int, attempts: int = 20) -> int:
    """Return the first free port in [start_port, start_port + attempts)."""
    for port in range(start_port, start_port + attempts):
        if not port_is_busy(port):
            return port
    raise RuntimeError(
        f"No free port found between {start_port} and {start_port + attempts - 1}. "
        "Stop other servers or pass --port to choose a specific port."
    )


def rotate_log_if_needed() -> None:
    """Keep the log file under MAX_LOG_BYTES by rotating it once."""
    if LOG_FILE.exists() and LOG_FILE.stat().st_size > MAX_LOG_BYTES:
        backup = LOG_FILE.with_name("md-preview.1.log")
        if backup.exists():
            backup.unlink()
        LOG_FILE.rename(backup)


def wait_for_port(port: int, timeout_seconds: float = 5.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if port_is_busy(port):
            return True
        time.sleep(0.1)
    return False


def host_resolves(host: str) -> bool:
    try:
        socket.gethostbyname(host)
    except OSError:
        return False
    return True


def browser_base_url(port: int, override: str | None = None) -> str:
    if override:
        return override.format(port=port).rstrip("/")
    local_proxy_host = f"{port}.kit.test"
    if host_resolves(local_proxy_host):
        return f"https://{local_proxy_host}"
    return f"http://127.0.0.1:{port}"


def browser_url(port: int, preview_name: str, override_base_url: str | None = None) -> str:
    base = browser_base_url(port, override_base_url)
    return f"{base}/{quote(preview_name)}"


def open_browser(url: str) -> None:
    import platform
    system = platform.system()
    if system == "Darwin":
        subprocess.run(["open", url], check=True)
    elif system == "Linux":
        opener = shutil.which("xdg-open")
        if not opener:
            raise RuntimeError("No browser opener found. Install `xdg-utils`.")
        subprocess.run([opener, url], check=True)
    elif system == "Windows":
        os.startfile(url)  # type: ignore[attr-defined]
    else:
        raise RuntimeError(f"Unsupported platform: {system}")


def cleanup_preview_file(state: dict[str, Any] | None) -> None:
    if not state:
        return
    preview = state.get("preview")
    if preview:
        preview_path = Path(preview)
        if preview_path.exists():
            preview_path.unlink()
            sys.stderr.write(f"[md-preview] cleaned up {preview_path.name}\n")
            sys.stderr.flush()


def stop_running_server() -> bool:
    state = load_state()
    if not state:
        return False

    pid = int(state.get("pid", 0))
    if pid <= 0 or not process_is_running(pid):
        cleanup_preview_file(state)
        if STATE_FILE.exists():
            STATE_FILE.unlink()
        return False

    os.kill(pid, signal.SIGTERM)
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if not process_is_running(pid):
            break
        time.sleep(0.1)
    if process_is_running(pid):
        os.kill(pid, signal.SIGKILL)

    cleanup_preview_file(state)
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    return True


class PreviewRequestHandler(SimpleHTTPRequestHandler):
    def __init__(
        self,
        *args: Any,
        directory: str,
        preview_name: str,
        version_getter: Callable[[], str],
        close_state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self.preview_name = preview_name
        self.version_getter = version_getter
        self.close_state = close_state
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == VERSION_PATH:
            if self.close_state is not None:
                # Active poll → browser is alive; reset any pending unload signal
                self.close_state["last_poll_time"] = time.time()
                self.close_state["unload_signaled"] = False
            payload = f"{self.version_getter()}\n".encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path in {"", "/"}:
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", f"/{quote(self.preview_name)}")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return

        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == UNLOAD_PATH and self.close_state is not None:
            self.close_state["unload_signaled"] = True
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
        self.end_headers()

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format_string: str, *args: Any) -> None:
        sys.stderr.write(
            f"[md-preview] {self.log_date_time_string()} {format_string % args}\n"
        )
        sys.stderr.flush()


def serve(args: argparse.Namespace) -> int:
    markdown_path = resolve_markdown_path(args.file)
    preview_path = build_preview(markdown_path)
    version_box = {"value": str(time.time_ns())}
    stop_event = threading.Event()
    last_mtime_ns = markdown_path.stat().st_mtime_ns
    auto_close = getattr(args, "auto_close", False)

    close_state: dict[str, Any] | None = None
    if auto_close:
        close_state = {"last_poll_time": time.time(), "unload_signaled": False}

    def version_getter() -> str:
        return version_box["value"]

    def watcher() -> None:
        nonlocal last_mtime_ns
        while not stop_event.wait(args.interval):
            try:
                current_mtime_ns = markdown_path.stat().st_mtime_ns
            except FileNotFoundError:
                continue
            if current_mtime_ns == last_mtime_ns:
                continue
            try:
                build_preview(markdown_path)
            except Exception as exc:  # noqa: BLE001
                sys.stderr.write(f"[md-preview] rebuild failed: {exc}\n")
                sys.stderr.flush()
            else:
                last_mtime_ns = current_mtime_ns
                version_box["value"] = str(time.time_ns())
                sys.stderr.write(
                    f"[md-preview] refreshed {markdown_path.name} -> {preview_path.name}\n"
                )
                sys.stderr.flush()

    handler = lambda *handler_args, **handler_kwargs: PreviewRequestHandler(  # noqa: E731
        *handler_args,
        directory=str(markdown_path.parent),
        preview_name=preview_path.name,
        version_getter=version_getter,
        close_state=close_state,
        **handler_kwargs,
    )

    server = ReusableHTTPServer((DEFAULT_BIND_HOST, args.port), handler)
    base_url = browser_base_url(args.port, args.base_url)
    url = browser_url(args.port, preview_path.name, args.base_url)
    watcher_thread = threading.Thread(target=watcher, name="md-preview-watcher", daemon=True)

    def shutdown_server(*_: Any) -> None:
        stop_event.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    def auto_close_watchdog() -> None:
        # K8s-style: wait for initial delay (analogous to initialDelaySeconds)
        stop_event.wait(AUTO_CLOSE_INITIAL_DELAY)
        while not stop_event.is_set():
            assert close_state is not None
            elapsed = time.time() - close_state["last_poll_time"]
            unload = close_state["unload_signaled"]
            # failureThreshold: shorter after unload beacon, longer as idle fallback
            threshold = AUTO_CLOSE_POLL_TIMEOUT if unload else AUTO_CLOSE_IDLE_TIMEOUT
            if elapsed > threshold:
                reason = "unload beacon + no poll" if unload else "idle timeout"
                sys.stderr.write(f"[md-preview] browser closed ({reason}), shutting down\n")
                sys.stderr.flush()
                shutdown_server()
                break
            stop_event.wait(1.0)

    signal.signal(signal.SIGTERM, shutdown_server)
    signal.signal(signal.SIGINT, shutdown_server)

    state = {
        "pid": os.getpid(),
        "port": args.port,
        "file": str(markdown_path),
        "preview": str(preview_path),
        "base_url": base_url,
        "url": url,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "auto_close": auto_close,
    }
    write_state(state)

    sys.stderr.write(f"[md-preview] serving {markdown_path} at {url}\n")
    if auto_close:
        sys.stderr.write("[md-preview] auto-close enabled\n")
    sys.stderr.flush()

    watcher_thread.start()
    if auto_close:
        threading.Thread(
            target=auto_close_watchdog, name="md-preview-auto-close", daemon=True
        ).start()
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        stop_event.set()
        server.server_close()
        watcher_thread.join(timeout=1.0)
        remove_state_if_owned(os.getpid())
        if preview_path.exists():
            preview_path.unlink()
            sys.stderr.write(f"[md-preview] cleaned up {preview_path.name}\n")
            sys.stderr.flush()
    return 0


def start(args: argparse.Namespace) -> int:
    markdown_path = resolve_markdown_path(args.file)

    if stop_running_server():
        time.sleep(0.2)

    port = args.port
    if port_is_busy(port):
        new_port = find_free_port(port + 1)
        sys.stderr.write(f"[md-preview] port {port} is busy, using {new_port} instead\n")
        sys.stderr.flush()
        port = new_port

    build_preview(markdown_path)

    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "serve",
        str(markdown_path),
        "--port",
        str(port),
        "--interval",
        str(args.interval),
    ]
    if args.base_url:
        command.extend(["--base-url", args.base_url])
    if not getattr(args, "auto_close", True):
        command.append("--no-auto-close")

    rotate_log_if_needed()
    log_handle = LOG_FILE.open("a", encoding="utf-8")
    process = subprocess.Popen(  # noqa: S603
        command,
        cwd=str(markdown_path.parent),
        stdout=log_handle,
        stderr=log_handle,
        start_new_session=True,
    )

    if not wait_for_port(port):
        raise RuntimeError(f"Preview server did not start. Check log: {LOG_FILE}")

    url = browser_url(port, preview_name_for(markdown_path), args.base_url)
    if not args.no_open:
        open_browser(url)

    print(f"Preview server started for {markdown_path}")
    print(f"PID: {process.pid}")
    print(f"URL: {url}")
    print(f"Log: {LOG_FILE}")
    return 0


def restart(args: argparse.Namespace) -> int:
    file_arg = getattr(args, "file", None)
    if not file_arg:
        state = load_state()
        if state:
            file_arg = state.get("file")
    if not file_arg:
        print(
            "ERROR: No file to restart. Specify a file or run 'start' first.",
            file=sys.stderr,
        )
        return 1
    args.file = file_arg
    return start(args)


def build(args: argparse.Namespace) -> int:
    markdown_path = resolve_markdown_path(args.file)
    preview_path = build_preview(markdown_path)
    print(preview_path)
    return 0


def status(_: argparse.Namespace) -> int:
    state = load_state()
    if not state:
        print("No managed md-preview server is running.")
        return 0

    pid = int(state.get("pid", 0))
    if pid <= 0 or not process_is_running(pid):
        if STATE_FILE.exists():
            STATE_FILE.unlink()
        print("No managed md-preview server is running.")
        return 0

    print(f"PID: {pid}")
    print(f"Port: {state.get('port')}")
    print(f"File: {state.get('file')}")
    print(f"Preview: {state.get('preview')}")
    print(f"URL: {state.get('url')}")
    print(f"Started: {state.get('started_at')}")
    return 0


def stop(_: argparse.Namespace) -> int:
    if stop_running_server():
        print("Stopped md-preview server.")
    else:
        print("No managed md-preview server is running.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preview a local Markdown file in a browser with live reload."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    shared_file_parser = argparse.ArgumentParser(add_help=False)
    shared_file_parser.add_argument("file", help="Markdown file to preview")

    start_parser = subparsers.add_parser("start", parents=[shared_file_parser])
    start_parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    start_parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL,
        help="Polling interval in seconds",
    )
    start_parser.add_argument("--base-url", help="Browser base URL template, e.g. http://127.0.0.1:{port}")
    start_parser.add_argument("--no-open", action="store_true", help="Do not open a browser")
    start_parser.add_argument(
        "--no-auto-close",
        action="store_false",
        dest="auto_close",
        help="Keep the server running even after the browser tab is closed",
    )
    start_parser.set_defaults(func=start, auto_close=True)

    build_parser_cmd = subparsers.add_parser("build", parents=[shared_file_parser])
    build_parser_cmd.set_defaults(func=build)

    serve_parser = subparsers.add_parser("serve", parents=[shared_file_parser])
    serve_parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve_parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL,
        help="Polling interval in seconds",
    )
    serve_parser.add_argument("--base-url", help="Browser base URL template, e.g. http://127.0.0.1:{port}")
    serve_parser.add_argument(
        "--no-auto-close",
        action="store_false",
        dest="auto_close",
        help="Keep the server running even after the browser tab is closed",
    )
    serve_parser.set_defaults(func=serve, auto_close=True)

    restart_parser = subparsers.add_parser(
        "restart",
        help="Stop the running preview and start again (file is optional if a server is running)",
    )
    restart_parser.add_argument(
        "file",
        nargs="?",
        help="Markdown file to preview (defaults to the currently running file)",
    )
    restart_parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    restart_parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL,
        help="Polling interval in seconds",
    )
    restart_parser.add_argument(
        "--base-url", help="Browser base URL template, e.g. http://127.0.0.1:{port}"
    )
    restart_parser.add_argument("--no-open", action="store_true", help="Do not open a browser")
    restart_parser.add_argument(
        "--no-auto-close",
        action="store_false",
        dest="auto_close",
        help="Keep the server running even after the browser tab is closed",
    )
    restart_parser.set_defaults(func=restart, auto_close=True)

    status_parser = subparsers.add_parser("status")
    status_parser.set_defaults(func=status)

    stop_parser = subparsers.add_parser("stop")
    stop_parser.set_defaults(func=stop)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
