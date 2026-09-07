#!/usr/bin/env python3
"""FlowCore Daemon — background process manager with periodic Compliance Scan jobs.

Starts the FlowCore API as a daemon and executes periodic background scans
(Compliance Scan, Maturity Scan, Portfolio Scan) without requiring user intervention.

Usage:
    python3 daemon.py start      Start daemon
    python3 daemon.py stop       Stop daemon
    python3 daemon.py status     Check status
    python3 daemon.py restart    Restart daemon
    python3 daemon.py scan       Run single compliance scan
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PID_FILE = ROOT / "logs" / "flowcore.pid"
LOG_FILE = ROOT / "logs" / "flowcore.log"

# Ensure logs directory exists
ROOT.joinpath("logs").mkdir(exist_ok=True)


def run_compliance_scan() -> dict:
    """Run background portfolio compliance scan across all stored portfolios."""
    try:
        from storage.portfolio_repo import portfolio_repo
        from agents.compliance_events import FlowCoreEvent, EventType, event_bus
        from agents.compliance_orchestrator import orchestrator

        portfolios = portfolio_repo.list_portfolios()
        scanned = 0
        non_compliant = 0

        for p in portfolios:
            scanned += 1
            event = FlowCoreEvent(
                event_type=EventType.PORTFOLIO_CHANGED,
                client_id=p.get("client_id", "unknown"),
                portfolio_id=p.get("id", "unknown"),
                source="BackgroundDaemonScan",
                payload={"portfolio": p},
            )
            res = orchestrator.handle_portfolio_changed(event)
            if res.get("status") == "NON_COMPLIANT":
                non_compliant += 1

        return {"scanned": scanned, "non_compliant": non_compliant}
    except Exception as e:
        return {"error": str(e)}


def get_pid() -> int | None:
    """Read the PID from the pid file, return None if not running."""
    if not PID_FILE.exists():
        return None
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        PID_FILE.unlink(missing_ok=True)
        return None


def cmd_start() -> None:
    """Start the daemon."""
    pid = get_pid()
    if pid is not None:
        print(f"Daemon already running (PID {pid})")
        return

    print("Starting FlowCore daemon...")
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "flowcore.py"), "serve"],
        stdout=open(LOG_FILE, "a"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
        cwd=str(ROOT),
    )
    PID_FILE.write_text(str(proc.pid))
    time.sleep(1)

    if proc.poll() is None:
        print(f"Daemon started (PID {proc.pid})")
        print(f"API: http://127.0.0.1:8080")
        print(f"Logs: {LOG_FILE}")
        # Run immediate compliance scan upon startup
        scan_res = run_compliance_scan()
        print(f"Background Scan Status: {scan_res}")
    else:
        print("Failed to start daemon. Check logs:", LOG_FILE)


def cmd_stop() -> None:
    """Stop the daemon."""
    pid = get_pid()
    if pid is None:
        print("Daemon is not running")
        return

    print(f"Stopping daemon (PID {pid})...")
    try:
        os.kill(pid, signal.SIGTERM)
        time.sleep(2)
        if get_pid() is not None:
            os.kill(pid, signal.SIGKILL)
            time.sleep(0.5)
    except ProcessLookupError:
        pass

    PID_FILE.unlink(missing_ok=True)
    print("Daemon stopped")


def cmd_status() -> None:
    """Check daemon status."""
    pid = get_pid()
    if pid is None:
        print("Daemon is NOT running")
    else:
        print(f"Daemon is running (PID {pid})")
        if LOG_FILE.exists():
            print(f"Logs: {LOG_FILE}")


def cmd_restart() -> None:
    """Restart the daemon."""
    cmd_stop()
    time.sleep(1)
    cmd_start()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="FlowCore Daemon Manager")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("start", help="Start daemon")
    subparsers.add_parser("stop", help="Stop daemon")
    subparsers.add_parser("status", help="Check status")
    subparsers.add_parser("restart", help="Restart daemon")
    subparsers.add_parser("scan", help="Run compliance scan")

    args = parser.parse_args()

    if args.command == "start":
        cmd_start()
    elif args.command == "stop":
        cmd_stop()
    elif args.command == "status":
        cmd_status()
    elif args.command == "restart":
        cmd_restart()
    elif args.command == "scan":
        print("Running Compliance Scan...", run_compliance_scan())
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
