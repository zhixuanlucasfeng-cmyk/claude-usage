import argparse
import json
import threading
import time
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from claude_usage.aggregate import (
    aggregate_by_date,
    aggregate_by_project,
    aggregate_by_session,
    total_unpriced_count,
)
from claude_usage.html import render_dashboard
from claude_usage.scanner import UsageRecord, scan_projects_dir
from claude_usage.sources import scan_codex, scan_hermes
from claude_usage.widget import build_widget_data, read_claude_limits


def _default_projects_dir() -> Path:
    return Path.home() / ".claude" / "projects"


def _filter_since(records: list[UsageRecord], days: int | None) -> list[UsageRecord]:
    if days is None:
        return records
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return [r for r in records if r.timestamp >= cutoff]


def build_report(records: list[UsageRecord], top_n: int) -> str:
    by_project = aggregate_by_project(records)
    total_cost = sum(entry.total_cost for entry in by_project)
    session_count = len({r.session_id for r in records})

    lines = [
        f"Claude Code Usage Report ({session_count} session(s))",
        "",
        "By project:",
    ]
    for entry in by_project:
        lines.append(
            f"  {entry.key}  ${entry.total_cost:.2f}  "
            f"({entry.input_tokens} in / {entry.output_tokens} out / "
            f"{entry.cache_creation_input_tokens} cache-write / "
            f"{entry.cache_read_input_tokens} cache-read)"
        )

    lines.append("")
    lines.append("By day:")
    for entry in aggregate_by_date(records):
        lines.append(f"  {entry.key}  ${entry.total_cost:.2f}")

    lines.append("")
    lines.append(f"Top {top_n} sessions by cost:")
    for entry in aggregate_by_session(records, top_n):
        lines.append(f"  {entry.key}  ${entry.total_cost:.2f}")

    lines.append("")
    lines.append(f"Total: ${total_cost:.2f}")

    unpriced = total_unpriced_count(records)
    if unpriced:
        lines.append(f"({unpriced} record(s) skipped from cost totals — unrecognized model name)")

    return "\n".join(lines)


def load_records(projects_dir: Path, days: int | None) -> list[UsageRecord]:
    if not projects_dir.exists():
        raise FileNotFoundError(
            f"{projects_dir} does not exist — no Claude Code usage history found on this machine."
        )
    return _filter_since(scan_projects_dir(projects_dir), days)


def run(projects_dir: Path, days: int | None, top_n: int) -> str:
    return build_report(load_records(projects_dir, days), top_n)


def _logs_version(projects_dir: Path) -> str:
    """Cheap change signal: newest log mtime plus file count."""
    files = list(projects_dir.rglob("*.jsonl"))
    return f"{max((f.stat().st_mtime for f in files), default=0)}:{len(files)}"


def _widget_loop(projects_dir: Path, out: dict) -> None:
    """Keep out["json"] fresh for the desktop widget (runs in a thread)."""
    codex_dir = Path.home() / ".codex" / "sessions"
    hermes_db = Path.home() / ".hermes" / "state.db"
    # Written by the Claude Code status line script (~/.claude/hooks/usage-statusline.sh).
    claude_limits_file = Path.home() / "Library" / "Application Support" / "ClaudeUsageWidget" / "claude-limits.json"
    version, claude = None, []
    while True:
        try:
            v = _logs_version(projects_dir)
            if v != version:  # Claude logs are re-scanned only when they change
                claude, version = scan_projects_dir(projects_dir), v
            data = build_widget_data(claude, scan_codex(codex_dir), scan_hermes(hermes_db), date.today())
            data["claude_limit"] = read_claude_limits(claude_limits_file)
            out["json"] = json.dumps(data).encode()
        except Exception as e:  # never let the widget feed die; show the error instead
            out["json"] = json.dumps({"error": str(e)}).encode()
        time.sleep(15)


def serve(projects_dir: Path, days: int | None, top_n: int, port: int, open_browser: bool) -> None:
    widget: dict = {}
    threading.Thread(target=_widget_loop, args=(projects_dir, widget), daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/widget.json":
                if "json" not in widget:
                    self.send_error(503, "warming up")
                    return
                body, kind = widget["json"], "application/json"
            elif self.path == "/version":
                body, kind = _logs_version(projects_dir).encode(), "text/plain"
            elif self.path == "/":
                page = render_dashboard(load_records(projects_dir, days), top_n, live=True)
                body, kind = page.encode("utf-8"), "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args) -> None:  # keep the terminal quiet
            pass

    load_records(projects_dir, days)  # fail fast if there is no history
    # Bound to localhost only: the page lists your project paths.
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Claude usage dashboard running at {url}  (Ctrl+C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(prog="claude-usage")
    subparsers = parser.add_subparsers(dest="command", required=True)

    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("--days", type=int, default=None)
    report_parser.add_argument("--top", type=int, default=10)

    html_parser = subparsers.add_parser("html", help="write a visual dashboard and open it")
    html_parser.add_argument("--days", type=int, default=None)
    html_parser.add_argument("--top", type=int, default=15)
    html_parser.add_argument("--out", type=Path, default=Path.home() / "claude-usage.html")
    html_parser.add_argument("--no-open", action="store_true")

    serve_parser = subparsers.add_parser("serve", help="run the live dashboard locally")
    serve_parser.add_argument("--days", type=int, default=None)
    serve_parser.add_argument("--top", type=int, default=15)
    serve_parser.add_argument("--port", type=int, default=8899)
    serve_parser.add_argument("--no-open", action="store_true")

    args = parser.parse_args()

    if args.command == "serve":
        try:
            serve(_default_projects_dir(), args.days, args.top, args.port, not args.no_open)
        except FileNotFoundError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
        except OSError as e:
            print(f"ERROR: cannot listen on port {args.port} ({e}). Already running? Try --port.", file=sys.stderr)
            sys.exit(1)
        return

    try:
        records = load_records(_default_projects_dir(), args.days)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.command == "html":
        args.out.write_text(render_dashboard(records, args.top), encoding="utf-8")
        print(f"Wrote {args.out}")
        if not args.no_open:
            webbrowser.open(args.out.resolve().as_uri())
        return

    print(build_report(records, args.top))


if __name__ == "__main__":
    main()
