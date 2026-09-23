"""
Main entry point for the InboxIQ local server application.
"""

import sys
from pathlib import Path
import uvicorn

# Ensure backend/src is on the Python path
SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from settings import settings


def main():
    print(
        f"Starting InboxIQ Local Server at http://{settings.API_HOST}:{settings.API_PORT} "
        f"(auto-reload: {'ON' if settings.API_RELOAD else 'OFF'})"
    )
    uvicorn.run(
        "api.server:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.API_RELOAD,
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


if __name__ == "__main__":
    main()