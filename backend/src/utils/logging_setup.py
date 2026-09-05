import logging
from pathlib import Path


def get_logger(
    name: str = "app",
    log_file: str = "app.log",
    log_dir: str = "logs",
    console_level: int = logging.DEBUG,
    file_level: int = logging.INFO,
) -> logging.Logger:

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger

    # Create log directory
    Path(log_dir).mkdir(parents=True, exist_ok=True)

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
        Path(log_dir) / log_file,
        encoding="utf-8"
    )
    file_handler.setLevel(file_level)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger