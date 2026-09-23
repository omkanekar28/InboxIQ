import time
from pathlib import Path
from typing import Optional, Callable, Any
import requests
from tqdm import tqdm
from utils import get_logger

logger = get_logger(__name__)


def download_file(
    url: str,
    output_dir: str,
    show_progress: bool = True,
    progress_callback: Optional[Callable[..., None]] = None,
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = url.split("/")[-1].split("?")[0]
    output_path = output_dir / filename

    response = requests.get(url, stream=True)
    response.raise_for_status()

    total_size = int(response.headers.get("content-length", 0))

    # Skip download if existing file has the same size
    if output_path.exists():
        existing_size = output_path.stat().st_size

        if total_size and existing_size == total_size:
            logger.info(
                "File already exists with matching size, skipping download: %s",
                output_path,
            )
            if progress_callback:
                try:
                    progress_callback(total_size, total_size, 0.0)
                except TypeError:
                    try:
                        progress_callback(total_size, total_size)
                    except Exception:
                        pass
                except Exception:
                    pass
            return output_path

        logger.warning(
            "Existing file has different size (%d vs %d), replacing: %s",
            existing_size,
            total_size,
            output_path,
        )
        output_path.unlink()

    chunk_size = 65536  # 64 KB buffer for high-throughput downloads
    downloaded = 0
    start_time = time.time()
    last_callback_time = 0.0

    with open(output_path, "wb") as f:
        iterator = response.iter_content(chunk_size=chunk_size)

        if show_progress:
            iterator = tqdm(
                iterator,
                total=(total_size // chunk_size) + 1 if total_size else None,
                unit="B",
                unit_scale=True,
                desc=filename,
            )

        for chunk in iterator:
            if not chunk:
                continue
            f.write(chunk)
            downloaded += len(chunk)

            now = time.time()
            if progress_callback and (
                now - last_callback_time >= 0.15
                or (total_size and downloaded >= total_size)
            ):
                last_callback_time = now
                elapsed = now - start_time
                speed = downloaded / elapsed if elapsed > 0 else 0.0
                try:
                    progress_callback(downloaded, total_size, speed)
                except TypeError:
                    try:
                        progress_callback(downloaded, total_size)
                    except Exception:
                        pass
                except Exception:
                    pass

    # Ensure final 100% callback was dispatched
    if progress_callback and total_size:
        elapsed = max(time.time() - start_time, 0.001)
        speed = downloaded / elapsed
        try:
            progress_callback(downloaded, total_size, speed)
        except TypeError:
            try:
                progress_callback(downloaded, total_size)
            except Exception:
                pass
        except Exception:
            pass

    logger.info("Downloaded file: %s", output_path)

    return output_path