"""
LLM - thin wrapper around a local llama-cpp server.
"""

import time
import requests
from pathlib import Path
from typing import Optional
from settings import settings
from utils import get_logger
from bootstrap.setup_models import setup_models
from bootstrap.setup_llm_server import (
    install_llama_runtime,
    start_llama_server,
    stop_llama_server,
)

logger = get_logger(__name__)

_MODEL_FILENAME: dict[str, str] = {
    "balanced": settings.MODEL_DOWNLOAD_URL_BALANCED.split("/")[-1].split("?")[0],
    "lightweight": settings.MODEL_DOWNLOAD_URL_LIGHTWEIGHT.split("/")[-1].split("?")[0],
}


class LLM:
    """Local LLM client backed by a llama-cpp HTTP server."""

    def __init__(
        self,
        model_type: Optional[str] = None,
        *,
        server_startup_timeout: int = 60,
    ) -> None:
        """Intialises the LLM."""
        self._model_type: str = model_type or settings.MODEL_TYPE
        if self._model_type not in ("balanced", "lightweight"):
            raise ValueError(
                f"model_type must be 'balanced' or 'lightweight', got {self._model_type!r}"
            )

        self._port: int = settings.LLAMA_CPP_SERVER_PORT_NO
        self._base_url: str = f"http://127.0.0.1:{self._port}"
        self._server_startup_timeout: int = server_startup_timeout
        self._ready: bool = False

    def setup(self) -> None:
        """Download both GGUF models and install the llama-cpp runtime."""
        logger.info("LLM.setup() — downloading models...")
        setup_models(
            balanced_model_url=settings.MODEL_DOWNLOAD_URL_BALANCED,
            lightweight_model_url=settings.MODEL_DOWNLOAD_URL_LIGHTWEIGHT,
            models_store_dir=settings.MODEL_STORE_DIR,
        )

        logger.info("LLM.setup() — installing llama-cpp runtime...")
        install_llama_runtime(
            url=settings.LLAMA_CPP_BINARIES_URL,
            extract_dir=settings.LLAMA_CPP_BINARIES_STORE_DIR,
        )
        logger.info("LLM.setup() — done.")

    def start(self) -> None:
        """Launch the llama-cpp server and block until it is healthy."""
        model_filename = _MODEL_FILENAME[self._model_type]
        model_filepath = str(Path(settings.MODEL_STORE_DIR) / model_filename)
        llama_server_filepath = str(
            Path(settings.LLAMA_CPP_BINARIES_STORE_DIR) / "llama-server.exe"
        )

        logger.info(
            "LLM.start() — launching server with model=%s on port=%d",
            model_filename,
            self._port,
        )

        start_llama_server(
            llama_server_filepath=llama_server_filepath,
            model_filepath=model_filepath,
            port=self._port,
            context_window_size=settings.LLAMA_CPP_SERVER_CONTEXT_WINDOW_SIZE,
            n_batch=settings.LLAMA_CPP_SERVER_N_BATCH,
            n_threads=settings.LLAMA_CPP_SERVER_N_THREADS,
        )

        self._wait_for_server()

    def stop(self) -> None:
        """Terminate the llama-cpp server process."""
        self._ready = False
        stop_llama_server()

    def prompt(
        self,
        prompt: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.7,
        stop: Optional[list[str]] = None,
    ) -> str:
        """
        Send a plain-text prompt and return the completion string.
        Uses the ``/v1/completions`` endpoint (raw text in, raw text out).
        """
        self._assert_ready()

        payload: dict = {
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if stop:
            payload["stop"] = stop

        response = requests.post(
            f"{self._base_url}/v1/completions",
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["text"]

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
        temperature: float = 0.7,
        stop: Optional[list[str]] = None,
    ) -> str:
        """
        Send a list of chat messages and return the assistant reply string.

        Each message must be a dict with ``"role"`` and ``"content"`` keys,
        e.g. ``[{"role": "user", "content": "Hello!"}]``.

        Uses the ``/v1/chat/completions`` endpoint (OpenAI-compatible).
        """
        self._assert_ready()

        payload: dict = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if stop:
            payload["stop"] = stop

        response = requests.post(
            f"{self._base_url}/v1/chat/completions",
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def _wait_for_server(self, poll_interval: float = 1.0) -> None:
        """Poll ``/health`` until the server is ready or timeout expires."""
        health_url = f"{self._base_url}/health"
        deadline = time.time() + self._server_startup_timeout

        logger.info(
            "Waiting for llama-cpp server to become healthy (timeout=%ds)...",
            self._server_startup_timeout,
        )

        while time.time() < deadline:
            try:
                resp = requests.get(health_url, timeout=2)
                if resp.status_code == 200:
                    self._ready = True
                    logger.info("llama-cpp server is healthy.")
                    return
            except requests.exceptions.RequestException:
                pass

            time.sleep(poll_interval)

        raise TimeoutError(
            f"llama-cpp server did not become healthy within "
            f"{self._server_startup_timeout}s."
        )

    def _assert_ready(self) -> None:
        if not self._ready:
            raise RuntimeError(
                "LLM server is not running. Call start() first."
            )


# FOR DEBUGGING
if __name__ == "__main__":
    llm = LLM()

    llm.setup()
    llm.start()

    response = llm.prompt("What is 2 + 2?")
    print("[prompt] response:", response)

    # reply = llm.chat([
    #     {"role": "system", "content": "You are a concise assistant."},
    #     {"role": "user", "content": "Summarise the French Revolution in one sentence."},
    # ])
    # print("[chat] response:", reply)

    llm.stop()
