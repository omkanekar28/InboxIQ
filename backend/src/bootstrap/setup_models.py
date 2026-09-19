import time
import shutil
from utils import get_logger, download_file

logger = get_logger(name=__name__)


def setup_models(
    balanced_model_url: str, 
    lightweight_model_url: str, 
    models_store_dir: str
):
    try:
        balanced_start_time = time.time()
        logger.info(f"Download model (balanced) ...")
        download_file(
            url=balanced_model_url,
            output_dir=models_store_dir,
        )
        logger.info(f"Download model (balanced) completed in {time.time() - balanced_start_time:.2f} seconds")

        lightweight_start_time = time.time()
        logger.info(f"Download model (lightweight) ...")
        download_file(
            url=lightweight_model_url,
            output_dir=models_store_dir,
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
#         models_store_dir=os.path.join(settings.TEST_DIR, "models")
#     )