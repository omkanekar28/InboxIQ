from pathlib import Path
import requests
from tqdm import tqdm
from utils import get_logger

logger = get_logger(__name__)


def download_file(
    url: str,
    output_dir: str,
    show_progress: bool = True,
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
            return output_path

        logger.warning(
            "Existing file has different size (%d vs %d), replacing: %s",
            existing_size,
            total_size,
            output_path,
        )
        output_path.unlink()

    with open(output_path, "wb") as f:
        iterator = response.iter_content(chunk_size=8192)

        if show_progress:
            iterator = tqdm(
                iterator,
                total=(total_size // 8192) + 1 if total_size else None,
                unit="B",
                unit_scale=True,
                desc=filename,
            )

        for chunk in iterator:
            f.write(chunk)

    logger.info("Downloaded file: %s", output_path)

    return output_path