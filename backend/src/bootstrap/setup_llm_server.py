import os
import time
import requests
import zipfile
import tempfile
import subprocess
from pathlib import Path
from typing import Optional, Any
from tqdm import tqdm
from utils import get_logger

logger = get_logger(__name__)


def is_gpu_available() -> bool:
    """
    Detect if an NVIDIA CUDA-capable GPU is available on the machine.
    Uses ctypes to query CUDA driver APIs directly, falling back to nvidia-smi.
    """
    try:
        if os.name == "nt":
            import ctypes
            cuda = ctypes.windll.nvcuda
        else:
            import ctypes
            cuda = ctypes.cdll.LoadLibrary("libcuda.so")

        if cuda.cuInit(0) == 0:
            count = ctypes.c_int()
            if cuda.cuDeviceGetCount(ctypes.byref(count)) == 0 and count.value > 0:
                return True
    except Exception:
        pass

    try:
        res = subprocess.run(
            ["nvidia-smi"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return res.returncode == 0
    except Exception:
        return False


def install_llama_runtime(
    url: str,
    extract_dir: str | Path,
    progress_callback: Optional[Any] = None,
    show_progress: bool = True,
) -> Path | None:
    """Install the llama runtime if it is not already installed."""

    try:
        extract_dir = Path(extract_dir)
        runtime_filepath = extract_dir / "llama-server.exe"
        installed_url_file = extract_dir / ".installed_url"

        # Already installed with matching URL
        if runtime_filepath.exists() and installed_url_file.exists():
            try:
                installed_url = installed_url_file.read_text(encoding="utf-8").strip()
                if installed_url == url:
                    logger.info(
                        f"Llama runtime is already installed at: {runtime_filepath}"
                    )
                    os.environ["LLM_SERVER_BINARY"] = str(runtime_filepath)
                    if progress_callback:
                        try:
                            progress_callback(100, 100, 0.0, "installed")
                        except TypeError:
                            try:
                                progress_callback(100, 100)
                            except Exception:
                                pass
                        except Exception:
                            pass
                    return runtime_filepath
            except Exception:
                pass

        logger.info(
            f"Installing llama runtime from {url} "
            f"to {extract_dir}..."
        )

        extract_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_zip_path = Path(temp_dir) / "llama.zip"

            # Download
            logger.info(f"Downloading from {url}...")

            with requests.get(url, stream=True, timeout=(10, 60)) as response:
                response.raise_for_status()

                total_size = int(
                    response.headers.get("content-length", 0)
                )

                downloaded = 0
                last_logged = 0
                log_step = 10 * 1024 * 1024
                start_time = time.time()
                last_callback_time = 0.0

                with temp_zip_path.open("wb") as f:
                    iterator = response.iter_content(chunk_size=64 * 1024)

                    if show_progress:
                        iterator = tqdm(
                            iterator,
                            total=total_size,
                            unit="B",
                            unit_scale=True,
                            desc="Downloading llama runtime",
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
                                progress_callback(downloaded, total_size, speed, "downloading")
                            except TypeError:
                                try:
                                    progress_callback(downloaded, total_size)
                                except Exception:
                                    pass
                            except Exception:
                                pass

                        if (
                            not show_progress
                            and (
                                downloaded - last_logged >= log_step
                                or (
                                    total_size
                                    and downloaded == total_size
                                )
                            )
                        ):
                            last_logged = downloaded

                            if total_size > 0:
                                logger.info(
                                    f"Downloaded "
                                    f"{downloaded / (1024 * 1024):.1f}/"
                                    f"{total_size / (1024 * 1024):.1f} MB "
                                    f"({(downloaded / total_size) * 100:.0f}%)"
                                )
                            else:
                                logger.info(
                                    f"Downloaded "
                                    f"{downloaded / (1024 * 1024):.1f} MB"
                                )

            # Extract
            logger.info("Extracting runtime archive...")
            if progress_callback:
                try:
                    progress_callback(total_size, total_size, 0.0, "extracting")
                except TypeError:
                    try:
                        progress_callback(total_size, total_size)
                    except Exception:
                        pass
                except Exception:
                    pass

            with zipfile.ZipFile(temp_zip_path, "r") as zip_ref:
                zip_ref.extractall(extract_dir)

        try:
            installed_url_file.write_text(url, encoding="utf-8")
        except Exception as e:
            logger.warning(f"Could not write .installed_url marker file: {e}")

        logger.info(f"Runtime installed to {extract_dir}")

        os.environ["LLM_SERVER_BINARY"] = str(runtime_filepath)

        return runtime_filepath

    except Exception as e:
        logger.error(f"Installation failed: {e}")
        raise


def get_gpu_info() -> dict[str, Any]:
    """
    Get detailed GPU information (name, VRAM in MB) using nvidia-smi.
    Falls back gracefully if nvidia-smi is unavailable or no GPU exists.
    """
    info: dict[str, Any] = {
        "gpu_available": False,
        "gpu_name": None,
        "vram_mb": None,
    }
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=5,
        )
        if res.returncode == 0 and res.stdout.strip():
            line = res.stdout.strip().splitlines()[0]
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2:
                info["gpu_available"] = True
                info["gpu_name"] = parts[0]
                try:
                    info["vram_mb"] = int(float(parts[1]))
                except ValueError:
                    info["vram_mb"] = None
                return info
    except Exception as e:
        logger.debug(f"Failed to query nvidia-smi for GPU details: {e}")

    if is_gpu_available():
        info["gpu_available"] = True

    return info


_running_server_process: Optional[subprocess.Popen] = None


def start_llama_server(
    llama_server_filepath: str,
    model_filepath: str,
    port: int = 8000,
    context_window_size: int = 16000,
    n_batch: int = 512,
    n_threads: int = 4,
    n_gpu_layers: int = 0,
) -> subprocess.Popen:
    """Starts the llama-cpp server with the given model and port."""
    global _running_server_process
    try:
        logger.info(
            "Starting llama-cpp server (n_gpu_layers=%d)...", n_gpu_layers
        )
        log_dir = Path(llama_server_filepath).parent.parent / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = open(log_dir / "llama_server.log", "a", encoding="utf-8")

        proc = subprocess.Popen(
            [
                llama_server_filepath,
                "-m",
                model_filepath,
                "-c",
                str(context_window_size),
                "-b",
                str(n_batch),
                "--threads",
                str(n_threads),
                "--port",
                str(port),
                "-ngl",
                str(n_gpu_layers),
            ],
            stdout=log_file,
            stderr=log_file,
        )
        _running_server_process = proc
        logger.info(f"Llama-cpp server started (PID: {proc.pid}).")
        return proc
    except Exception as e:
        logger.error(f"Failed to start llama-cpp server: {e}")
        raise


def stop_llama_server(
    proc: Optional[subprocess.Popen] = None,
    pid: Optional[int] = None,
) -> None:
    """Stops the llama-cpp server process by PID if available, falling back to system-wide kill."""
    global _running_server_process
    target_pid = pid or (proc.pid if proc else None) or (_running_server_process.pid if _running_server_process else None)
    try:
        if target_pid:
            logger.info(f"Stopping llama-cpp server (PID: {target_pid})...")
            subprocess.run(
                ["cmd.exe", "/c", "taskkill", "/F", "/PID", str(target_pid)],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            logger.info("Stopping llama-cpp server (system-wide fallback)...")
            subprocess.run(
                ["cmd.exe", "/c", "taskkill", "/F", "/IM", "llama-server.exe"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        time.sleep(0.5)
        _running_server_process = None
        logger.info("Llama-cpp server stopped.")

    except Exception as e:
        logger.error(f"Failed to stop llama-cpp server: {e}")
        raise

# FOR DEBUGGING
# if __name__ == "__main__":
#     from settings import settings
#     from pathlib import Path

#     install_llama_runtime(
#         url=settings.LLAMA_CPP_BINARIES_URL,
#         extract_dir=Path(settings.LLAMA_CPP_BINARIES_STORE_DIR),
#     )

#     start_llama_server(
#         llama_server_filepath=os.path.join(
#             settings.LLAMA_CPP_BINARIES_STORE_DIR, "llama-server.exe"
#         ), 
#         model_filepath=os.path.join(settings.MODEL_STORE_DIR, "LFM2.5-230M-Q4_K_M.gguf"),
#         port=settings.LLAMA_CPP_SERVER_PORT_NO,
#         context_window_size=settings.LLAMA_CPP_SERVER_CONTEXT_WINDOW_SIZE,
#         n_batch=settings.LLAMA_CPP_SERVER_N_BATCH,
#         n_threads=settings.LLAMA_CPP_SERVER_N_THREADS,
#     )

#     stop_llama_server()