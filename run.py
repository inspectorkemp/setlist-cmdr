#!/usr/bin/env python3
"""
Setlist Navigator - Local Dev Runner
Works on Windows, macOS, and Linux.

Usage:
    python run.py
    python run.py --port 8080
    python run.py --no-browser
    python run.py --no-reload
"""

import argparse
import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT      = Path(__file__).parent
VENV_DIR  = ROOT / "venv"
REQ_FILE  = ROOT / "requirements.txt"

def venv_python():
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"

def venv_uvicorn():
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "uvicorn.exe"
    return VENV_DIR / "bin" / "uvicorn"

def ensure_venv():
    if not VENV_DIR.exists():
        print("Creating virtual environment...")
        venv.create(str(VENV_DIR), with_pip=True)
        print("  Virtual environment created")
    else:
        print("Virtual environment already exists, skipping")

def ensure_deps():
    print("Installing / verifying dependencies...")
    subprocess.check_call(
        [str(venv_python()), "-m", "pip", "install", "-q", "--upgrade", "pip"],
        cwd=ROOT
    )
    subprocess.check_call(
        [str(venv_python()), "-m", "pip", "install", "-q", "-r", str(REQ_FILE)],
        cwd=ROOT
    )
    print("  Dependencies ready")

def open_browser(port):
    import threading, time, webbrowser
    def _open():
        time.sleep(1.5)
        leader_url = "http://localhost:{}/leader".format(port)
        stage_url  = "http://localhost:{}/".format(port)
        print("\n  Leader view  -> {}".format(leader_url))
        print("  Musician URL -> {}\n".format(stage_url))
        webbrowser.open(leader_url)
    threading.Thread(target=_open, daemon=True).start()

def run_server(port, reload):
    cmd = [str(venv_uvicorn()), "main:app", "--host", "0.0.0.0", "--port", str(port)]
    if reload:
        cmd.append("--reload")
    print("\n" + "="*48)
    print("  Setlist Navigator running on port {}".format(port))
    print("="*48)
    subprocess.run(cmd, cwd=ROOT)

def main():
    parser = argparse.ArgumentParser(description="Run Setlist Navigator locally")
    parser.add_argument("--port",       type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--no-reload",  action="store_true")
    args = parser.parse_args()

    print("\nSetlist Navigator - Dev Runner\n")

    ensure_venv()
    ensure_deps()

    if not args.no_browser:
        open_browser(args.port)

    reload = not args.no_reload
    if reload:
        print("  (auto-reload on - edit .py or .html to restart)\n")

    run_server(args.port, reload)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nStopped.\n")
