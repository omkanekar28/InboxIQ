# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from pathlib import Path

# Paths relative to spec file directory (packaging/)
PACKAGING_DIR = Path(SPECPATH).resolve()
ROOT_DIR = PACKAGING_DIR.parent
BACKEND_SRC = ROOT_DIR / "backend" / "src"
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

FRONTEND_DIR = ROOT_DIR / "frontend"

datas = [
    (str(FRONTEND_DIR), "frontend"),
    (str(PACKAGING_DIR / "credentials.json"), "."),
    (str(PACKAGING_DIR / "icon.ico"), "."),
    (str(PACKAGING_DIR / "icon.png"), "."),
]
datas += collect_data_files('webview')

binaries = collect_dynamic_libs('webview')

hiddenimports = [
    "webview",
    "webview.platforms",
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",
    "clr",
    "clr_loader",
    "pythonnet",
    "uvicorn",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.logging",
    "fastapi",
    "fastapi.staticfiles",
    "starlette",
    "starlette.routing",
    "starlette.middleware",
    "starlette.middleware.cors",
    "starlette.staticfiles",
    "pydantic",
    "pydantic_settings",
    "pystray",
    "pystray._win32",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "google.auth",
    "google.auth.transport",
    "google.auth.transport.requests",
    "google.oauth2",
    "google.oauth2.credentials",
    "google_auth_oauthlib",
    "google_auth_oauthlib.flow",
    "googleapiclient",
    "googleapiclient.discovery",
    "googleapiclient.errors",
    "sqlite3",
    "requests",
    "tqdm",
    "webbrowser",
    "main",
    "settings",
    "tray",
    "api",
    "api.server",
    "api.endpoints",
    "api.models",
    "api.models.chat",
    "api.models.setup",
    "api.models.sync",
    "agent",
    "agent.llm",
    "agent.system_prompt",
    "agent.tools",
    "bootstrap",
    "bootstrap.setup_models",
    "bootstrap.setup_llm_server",
    "storage",
    "storage.database",
    "sync",
    "sync.gmail_sync",
    "utils",
    "utils.logging_setup",
    "utils.file_utils",
    "utils.datetime_functions",
    "utils.llm_utils",
]

a = Analysis(
    [str(BACKEND_SRC / "main.py")],
    pathex=[str(BACKEND_SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "notebook"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="InboxIQ",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PACKAGING_DIR / "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="InboxIQ",
)
