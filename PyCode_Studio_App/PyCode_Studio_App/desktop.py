"""Optional native desktop window for PyCode Studio (requires pywebview)."""
import os
import threading
import time
import urllib.request
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
PORT = int(os.getenv("PYCODE_PORT", "8765"))


def serve() -> None:
    uvicorn.run("app:app", host="127.0.0.1", port=PORT, log_level="warning")


def wait_for_server() -> None:
    url = f"http://127.0.0.1:{PORT}/api/health"
    for _ in range(100):
        try:
            with urllib.request.urlopen(url, timeout=0.5):
                return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("O servidor local não iniciou a tempo.")


def main() -> None:
    try:
        import webview
    except ImportError as exc:
        raise SystemExit("Instale as dependências com iniciar_desktop.bat ou pip install -r requirements-desktop.txt.") from exc
    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    wait_for_server()
    webview.create_window(
        "PyCode Studio — Python IDE",
        f"http://127.0.0.1:{PORT}",
        width=1440,
        height=920,
        min_size=(1000, 680),
        text_select=True,
    )
    webview.start()


if __name__ == "__main__":
    main()
