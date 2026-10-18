"""Entry point: `uv run scriptoria` serves the app on 127.0.0.1:8701 and opens it."""
from __future__ import annotations

from . import config
from .api import create_app

app = create_app()
HOST, PORT = config.HOST, config.PORT


def _open_browser(url: str) -> None:
    """Open the reader without the browser's own console chatter (Chromium
    prints zygote/session messages when handing off to an open window)."""
    import shutil
    import subprocess
    import sys
    import webbrowser
    opener = shutil.which("xdg-open") if sys.platform.startswith("linux") else None
    if opener:
        subprocess.Popen([opener, url], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    else:
        webbrowser.open(url)


def _already_running() -> bool:
    import socket
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex((HOST, PORT)) == 0


def run():
    import threading
    import uvicorn
    url = f"http://{HOST}:{PORT}"
    if _already_running():                     # e.g. launcher clicked twice
        print(f"Scriptoria is already running at {url}; opening it.")
        _open_browser(url)
        return
    threading.Timer(1.0, _open_browser, args=(url,)).start()
    print(f"Scriptoria running at {url}  (Ctrl+C to stop)")
    print(f"  notes & profiles: {config.user_db()}")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    run()
