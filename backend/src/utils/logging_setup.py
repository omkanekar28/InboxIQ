import logging
from pathlib import Path

# Always anchor default log dir to project root (InboxIQ/logs)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LOG_DIR = PROJECT_ROOT / "backend" / "logs"


def get_logger(
    name: str = "app",
    log_file: str = "app.log",
    log_dir: str | Path = DEFAULT_LOG_DIR,
    console_level: int = logging.DEBUG,
    file_level: int = logging.INFO,
) -> logging.Logger:

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger

    # Create log directory
    log_path = Path(log_dir).resolve()
    log_path.mkdir(parents=True, exist_ok=True)

    # Format
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)

    # File handler
    file_handler = logging.FileHandler(
        log_path / log_file,
        encoding="utf-8"
    )
    file_handler.setLevel(file_level)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger