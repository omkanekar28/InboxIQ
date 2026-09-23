from typing import Optional, Callable
import time
import shutil
from utils import get_logger, download_file

logger = get_logger(name=__name__)


def setup_models(
    balanced_model_url: str, 
    lightweight_model_url: str, 
    models_store_dir: str,
    progress_callback: Optional[Callable[[dict], None]] = None,
):
    try:
        balanced_filename = balanced_model_url.split("/")[-1].split("?")[0]
        lightweight_filename = lightweight_model_url.split("/")[-1].split("?")[0]

        balanced_start_time = time.time()
        logger.info(f"Download model (balanced: {balanced_filename}) ...")

        def _cb_balanced(downloaded, total, speed=0.0):
            if progress_callback:
                try:
                    progress_callback({
                        "model_num": 1,
                        "total_models": 2,
                        "filename": balanced_filename,
                        "model_type": "Balanced Model (8B)",
                        "downloaded": downloaded,
                        "total": total,
                        "speed": speed,
                    })
                except Exception:
                    pass

        download_file(
            url=balanced_model_url,
            output_dir=models_store_dir,
            progress_callback=_cb_balanced if progress_callback else None,
        )
        logger.info(f"Download model (balanced) completed in {time.time() - balanced_start_time:.2f} seconds")

        lightweight_start_time = time.time()
        logger.info(f"Download model (lightweight: {lightweight_filename}) ...")

        def _cb_lightweight(downloaded, total, speed=0.0):
            if progress_callback:
                try:
                    progress_callback({
                        "model_num": 2,
                        "total_models": 2,
                        "filename": lightweight_filename,
                        "model_type": "Lightweight Model (2.6B)",
                        "downloaded": downloaded,
                        "total": total,
                        "speed": speed,
                    })
                except Exception:
                    pass

        download_file(
            url=lightweight_model_url,
            output_dir=models_store_dir,
            progress_callback=_cb_lightweight if progress_callback else None,
        )
        logger.info(f"Download model (lightweight) completed in {time.time() - lightweight_start_time:.2f} seconds")

        logger.info(f"The models have been successfully downloaded to {models_store_dir}")
    except Exception as e:
        logger.error(f"Error downloading models: {e}. Cleaning up {models_store_dir} directory.")
        try:
            shutil.rmtree(models_store_dir)
            logger.info(f"Cleaned up {models_store_dir} directory.")
        except Exception as e:
            logger.error(f"Error cleaning up {models_store_dir} directory: {e}")


# FOR DEBUGGING
# if __name__ == "__main__":
#     import os
#     from settings import settings
#     setup_models(
#         balanced_model_url=settings.MODEL_DOWNLOAD_URL_BALANCED, 
#         lightweight_model_url=settings.MODEL_DOWNLOAD_URL_LIGHTWEIGHT, 
#         models_store_dir=os.path.join(settings.DB_STORE_DIR, "models")
#     )