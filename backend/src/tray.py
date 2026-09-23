"""
System tray icon management for InboxIQ.
Provides Open and Quit actions via pystray and Pillow.
"""

import os
import sys
import webbrowser
from pathlib import Path
from typing import Optional, Callable
from PIL import Image, ImageDraw
import pystray
from utils import get_logger

logger = get_logger(__name__)


def _load_or_generate_icon() -> Image.Image:
    # 1. Try bundled or packaged icon.ico / icon.png
    candidates = []
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", "."))
        candidates.extend([
            meipass / "icon.ico",
            meipass / "icon.png",
        ])

    # Source / dev candidates
    base_dir = Path(__file__).resolve().parent
    candidates.extend([
        base_dir.parent.parent / "packaging" / "icon.ico",
        base_dir.parent.parent / "packaging" / "icon.png",
        base_dir / "icon.ico",
        base_dir / "icon.png",
    ])

    for p in candidates:
        if p.exists():
            try:
                return Image.open(p)
            except Exception as e:
                logger.debug(f"Failed loading icon from {p}: {e}")

    # Fallback in-memory generated icon
    img = Image.new("RGBA", (64, 64), (17, 22, 17, 255))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([4, 4, 60, 60], radius=12, fill=(17, 22, 17, 255), outline=(0, 255, 65, 255), width=3)
    draw.rectangle([14, 18, 50, 44], fill=(10, 10, 10, 255), outline=(0, 255, 65, 255), width=2)
    draw.ellipse([27, 26, 37, 36], fill=(0, 255, 65, 255))
    return img


class SystemTray:
    def __init__(
        self,
        host: str,
        port: int,
        on_open: Optional[Callable] = None,
        on_quit: Optional[Callable] = None,
    ):
        self.host = host
        self.port = port
        self.url = f"http://{host}:{port}"
        self.on_open = on_open
        self.on_quit = on_quit
        self._icon: Optional[pystray.Icon] = None

    def open_app(self, icon=None, item=None):
        logger.info(f"Opening InboxIQ UI...")
        if self.on_open:
            try:
                self.on_open()
                return
            except Exception as e:
                logger.debug(f"on_open callback failed, falling back to browser: {e}")
        webbrowser.open(self.url)

    def open_logs(self, icon=None, item=None):
        try:
            from settings import USER_DATA_DIR
            log_dir = USER_DATA_DIR / "logs"
        except Exception:
            app_data = os.environ.get("APPDATA")
            log_dir = Path(app_data) / "InboxIQ" / "logs" if app_data else Path.home() / "InboxIQ" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(str(log_dir))
            else:
                webbrowser.open(log_dir.as_uri())
        except Exception as e:
            logger.warning(f"Could not open logs folder: {e}")

    def quit_app(self, icon=None, item=None):
        logger.info("Tray Quit requested. Shutting down InboxIQ...")
        if self.on_quit:
            try:
                self.on_quit()
            except Exception as e:
                logger.debug(f"on_quit callback failed: {e}")

        try:
            from api import endpoints
            endpoints.shutdown_services()
        except Exception as e:
            logger.warning(f"Error during shutdown: {e}")

        if self._icon:
            self._icon.stop()

        # Exit cleanly
        os._exit(0)

    def run(self):
        icon_img = _load_or_generate_icon()
        menu = pystray.Menu(
            pystray.MenuItem("Open InboxIQ", self.open_app, default=True),
            pystray.MenuItem("View Logs", self.open_logs),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit InboxIQ", self.quit_app),
        )
        self._icon = pystray.Icon(
            "InboxIQ",
            icon_img,
            "InboxIQ — Local AI Mail Assistant",
            menu=menu,
        )
        logger.info("System tray icon started.")
        self._icon.run()


def start_tray(
    host: str,
    port: int,
    on_open: Optional[Callable] = None,
    on_quit: Optional[Callable] = None,
):
    tray = SystemTray(host, port, on_open=on_open, on_quit=on_quit)
    tray.run()

