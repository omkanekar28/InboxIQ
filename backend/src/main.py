"""
Main entry point for the InboxIQ local server application.
Handles user data directory bootstrap, credential bundling,
browser auto-launch, system tray icon, and server execution.
"""

import os
import sys
import traceback
from pathlib import Path

# Redirect output streams to startup log in user data dir when in windowed mode
def _setup_stream_redirection():
    try:
        if sys.platform == "win32":
            app_data = os.environ.get("APPDATA")
            base = Path(app_data) if app_data else Path.home() / "AppData" / "Roaming"
        else:
            base = Path.home() / ".local" / "share"
        log_dir = base / "InboxIQ" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = open(log_dir / "startup.log", "a", encoding="utf-8")
        if sys.stdout is None or not hasattr(sys.stdout, "write"):
            sys.stdout = log_file
        if sys.stderr is None or not hasattr(sys.stderr, "write"):
            sys.stderr = log_file
    except Exception:
        pass

_setup_stream_redirection()

import argparse
import shutil
import time
import threading
import urllib.request
import webbrowser
import uvicorn

# Ensure backend/src is on the Python path
SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from settings import settings, USER_DATA_DIR
from utils import get_logger

logger = get_logger(__name__)

# Set Windows application model ID for proper taskbar grouping
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("InboxIQ.App.1.0")
    except Exception:
        pass


def _find_icon_path() -> Optional[str]:
    candidates = []
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", "."))
        candidates.extend([
            meipass / "icon.ico",
            meipass / "icon.png",
        ])
    candidates.extend([
        SRC_DIR.parent.parent / "packaging" / "icon.ico",
        SRC_DIR.parent.parent / "packaging" / "icon.png",
        SRC_DIR / "icon.ico",
    ])
    for p in candidates:
        if p.exists():
            return str(p)
    return None


def bootstrap_user_data_dir():
    """Ensure writable user data directories and bundled files exist."""
    # 1. Ensure core directories exist in %APPDATA%\InboxIQ
    subdirs = ["data", "models", "llama-cpp", "logs", "webview"]
    for sub in subdirs:
        (USER_DATA_DIR / sub).mkdir(parents=True, exist_ok=True)

    # 2. Check and copy bundled credentials.json if user does not have one
    user_creds = Path(settings.GMAIL_SYNC_CREDENTIALS_FILEPATH)
    if not user_creds.exists():
        candidates = []
        if getattr(sys, "frozen", False):
            meipass = Path(getattr(sys, "_MEIPASS", "."))
            candidates.extend([
                meipass / "credentials.json",
                meipass / "packaging" / "credentials.json",
            ])
        candidates.extend([
            SRC_DIR.parent.parent / "packaging" / "credentials.json",
            SRC_DIR / "credentials.json",
        ])

        for cand in candidates:
            if cand.exists():
                try:
                    shutil.copy2(cand, user_creds)
                    logger.info(f"Copied bundled credentials from {cand} to {user_creds}")
                    break
                except Exception as e:
                    logger.warning(f"Failed copying credentials from {cand}: {e}")

    # 3. Local dev fast-path: if repo has existing models/binaries and user dir does not, link or copy
    repo_models_dir = SRC_DIR.parent / "models"
    user_models_dir = Path(settings.MODEL_STORE_DIR)
    if repo_models_dir.exists() and user_models_dir.resolve() != repo_models_dir.resolve():
        for gguf in repo_models_dir.glob("*.gguf"):
            target = user_models_dir / gguf.name
            if not target.exists():
                try:
                    os.link(gguf, target)
                    logger.info(f"Linked existing model {gguf.name} into {user_models_dir}")
                except Exception:
                    try:
                        shutil.copy2(gguf, target)
                        logger.info(f"Copied existing model {gguf.name} into {user_models_dir}")
                    except Exception as e:
                        logger.debug(f"Could not copy model {gguf.name}: {e}")

    repo_llama_dir = SRC_DIR.parent / "llama-cpp"
    user_llama_dir = Path(settings.LLAMA_CPP_BINARIES_STORE_DIR)
    if repo_llama_dir.exists() and user_llama_dir.resolve() != repo_llama_dir.resolve():
        if not (user_llama_dir / "llama-server.exe").exists() and (repo_llama_dir / "llama-server.exe").exists():
            for item in repo_llama_dir.glob("*"):
                target = user_llama_dir / item.name
                if not target.exists():
                    try:
                        if item.is_file():
                            os.link(item, target)
                    except Exception:
                        try:
                            if item.is_file():
                                shutil.copy2(item, target)
                        except Exception:
                            pass


def open_browser_delayed(delay_seconds: float = 1.5):
    """Wait for API server to bind and open default web browser."""
    def _open():
        time.sleep(delay_seconds)
        url = f"http://{settings.API_HOST}:{settings.API_PORT}"
        try:
            webbrowser.open(url)
        except Exception as e:
            logger.debug(f"Failed to auto-open browser: {e}")

    threading.Thread(target=_open, daemon=True).start()


def wait_for_server_ready(url: str, timeout: float = 8.0) -> bool:
    """Poll health endpoint until server is ready."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.1)
    return False


def run_native_desktop(server: uvicorn.Server, app_url: str):
    """Launch native desktop window via pywebview on the main thread."""
    import webview

    force_quit = False
    window = webview.create_window(
        title="InboxIQ",
        url=app_url,
        width=1280,
        height=850,
        min_size=(960, 640),
        background_color="#0A0A0A",
        text_select=True,
        zoomable=True,
    )

    def on_closing():
        nonlocal force_quit
        if not force_quit:
            logger.info("Window close clicked. Hiding to system tray.")
            try:
                window.hide()
            except Exception as e:
                logger.debug(f"Error hiding window: {e}")
            return False  # Prevent window destruction
        return True

    window.events.closing += on_closing

    def on_open():
        try:
            window.show()
            window.restore()
        except Exception as e:
            logger.debug(f"Could not restore window: {e}")

    def on_quit():
        nonlocal force_quit
        force_quit = True
        logger.info("Shutting down from tray menu...")
        try:
            window.destroy()
        except Exception as e:
            logger.debug(f"Error destroying window: {e}")
        server.should_exit = True

    # Start system tray in background
    try:
        from tray import start_tray
        threading.Thread(
            target=start_tray,
            args=(settings.API_HOST, settings.API_PORT, on_open, on_quit),
            daemon=True,
        ).start()
    except Exception as e:
        logger.warning(f"Could not start system tray: {e}")

    icon_path = _find_icon_path()
    storage_path = str(USER_DATA_DIR / "webview")

    logger.info("Starting native desktop GUI event loop...")
    webview.start(icon=icon_path, storage_path=storage_path)

    # When webview loop finishes (e.g. on quit)
    logger.info("Desktop window closed. Exiting server...")
    server.should_exit = True
    try:
        from api import endpoints
        endpoints.shutdown_services()
    except Exception:
        pass
    time.sleep(0.3)
    os._exit(0)


def main():
    parser = argparse.ArgumentParser(description="InboxIQ — Local AI Mail Assistant")
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Open in default web browser instead of dedicated native desktop window",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run server in background without any window or browser",
    )
    args, _ = parser.parse_known_args()

    bootstrap_user_data_dir()

    is_frozen = getattr(sys, "frozen", False)
    app_url = f"http://{settings.API_HOST}:{settings.API_PORT}"
    print(
        f"Starting InboxIQ {'(Packaged)' if is_frozen else '(Development)'} at {app_url}"
    )

    # Headless mode
    if args.headless:
        from api.server import app
        uvicorn.run(app, host=settings.API_HOST, port=settings.API_PORT)
        return

    # Browser mode (for dev tools or explicit preference)
    if args.browser:
        if is_frozen:
            from tray import start_tray
            threading.Thread(
                target=start_tray,
                args=(settings.API_HOST, settings.API_PORT),
                daemon=True,
            ).start()
            open_browser_delayed(1.5)

        if settings.API_RELOAD:
            uvicorn.run(
                "api.server:app",
                host=settings.API_HOST,
                port=settings.API_PORT,
                reload=True,
                reload_dirs=[str(SRC_DIR)],
                reload_excludes=[
                    "*.log",
                    "*.db*",
                    "*token.json",
                    "*credentials.json",
                    "*.pyc",
                    "__pycache__",
                ],
            )
        else:
            from api.server import app
            uvicorn.run(app, host=settings.API_HOST, port=settings.API_PORT)
        return

    # Default Mode: Native Desktop Application Window
    from api.server import app
    server_config = uvicorn.Config(
        app,
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level="warning" if is_frozen else "info",
    )
    server = uvicorn.Server(server_config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    # Wait for server readiness before presenting window
    health_url = f"{app_url}/api/health"
    wait_for_server_ready(health_url, timeout=8.0)

    try:
        run_native_desktop(server, app_url)
    except Exception as e:
        logger.warning(f"Native desktop window failed to start ({e}). Falling back to browser...")
        open_browser_delayed(0.5)
        server_thread.join()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        trace = traceback.format_exc()
        try:
            logger.critical(f"Fatal crash during startup: {trace}")
        except Exception:
            pass
        try:
            with open(USER_DATA_DIR / "logs" / "crash.log", "a", encoding="utf-8") as f:
                f.write(f"\n{time.strftime('%Y-%m-%d %H:%M:%S')} CRASH:\n{trace}\n")
        except Exception:
            pass
        raise