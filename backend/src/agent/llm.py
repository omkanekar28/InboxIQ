"""
LLM - thin wrapper around a local llama-cpp server.
"""

import time
import requests
import json
import re
import logging
import subprocess
from pathlib import Path
from typing import Optional
from settings import settings
from utils import get_logger, skip_thinking_part_response
from bootstrap.setup_models import setup_models
from bootstrap.setup_llm_server import (
    install_llama_runtime,
    start_llama_server,
    stop_llama_server,
    is_gpu_available,
)
from .tools import TOOLS, TOOL_FUNCTIONS

logger = get_logger(__name__)

llm_output_logger = get_logger(
    "llm_output",
    log_file="llm_output.log", 
    file_level=logging.DEBUG,
    console_level=logging.INFO
)

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
        self._has_gpu: bool = is_gpu_available()
        self._process: Optional[subprocess.Popen] = None

    @property
    def model_type(self) -> str:
        return self._model_type

    @property
    def is_ready(self) -> bool:
        return self._ready

    def setup(self) -> None:
        """Download both GGUF models and install the llama-cpp runtime."""
        logger.info("LLM.setup() — downloading models...")
        setup_models(
            balanced_model_url=settings.MODEL_DOWNLOAD_URL_BALANCED,
            lightweight_model_url=settings.MODEL_DOWNLOAD_URL_LIGHTWEIGHT,
            models_store_dir=settings.MODEL_STORE_DIR,
        )

        runtime_url = (
            settings.LLAMA_CPP_CUDA_BINARIES_URL
            if self._has_gpu
            else settings.LLAMA_CPP_CPU_BINARIES_URL
        )
        logger.info(
            "LLM.setup() — installing llama-cpp runtime (GPU available: %s, url: %s)...",
            self._has_gpu,
            runtime_url,
        )
        install_llama_runtime(
            url=runtime_url,
            extract_dir=settings.LLAMA_CPP_BINARIES_STORE_DIR,
        )
        logger.info("LLM.setup() — done.")

    def __enter__(self) -> "LLM":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()

    def start(self, force_restart: bool = False) -> None:
        """Launch the llama-cpp server and block until it is healthy."""
        if not force_restart:
            # Check if server is already running and healthy
            try:
                resp = requests.get(f"{self._base_url}/health", timeout=1)
                if resp.status_code == 200:
                    logger.info("llama-cpp server is already running and healthy.")
                    self._ready = True
                    return
            except requests.exceptions.RequestException:
                pass

        model_filename = _MODEL_FILENAME[self._model_type]
        model_filepath = str(Path(settings.MODEL_STORE_DIR) / model_filename)
        llama_server_filepath = str(
            Path(settings.LLAMA_CPP_BINARIES_STORE_DIR) / "llama-server.exe"
        )

        n_gpu_layers = (
            settings.LLAMA_CPP_SERVER_N_GPU_LAYERS
            if settings.LLAMA_CPP_SERVER_N_GPU_LAYERS is not None
            else (-1 if self._has_gpu else 0)
        )

        logger.info(
            "LLM.start() — launching server with model=%s on port=%d (GPU=%s, n_gpu_layers=%d)",
            model_filename,
            self._port,
            self._has_gpu,
            n_gpu_layers,
        )

        self._process = start_llama_server(
            llama_server_filepath=llama_server_filepath,
            model_filepath=model_filepath,
            port=self._port,
            context_window_size=settings.LLAMA_CPP_SERVER_CONTEXT_WINDOW_SIZE,
            n_batch=settings.LLAMA_CPP_SERVER_N_BATCH,
            n_threads=settings.LLAMA_CPP_SERVER_N_THREADS,
            n_gpu_layers=n_gpu_layers,
        )

        self._wait_for_server()

    def stop(self) -> None:
        """Terminate the llama-cpp server process."""
        self._ready = False
        stop_llama_server(proc=self._process)
        self._process = None

    def switch_model(self, new_model_type: str) -> None:
        """
        Dynamically toggle active model between 'lightweight' and 'balanced'.
        Rejects 'balanced' if no GPU is available.
        """
        if new_model_type not in ("lightweight", "balanced"):
            raise ValueError(
                f"model_type must be 'lightweight' or 'balanced', got {new_model_type!r}"
            )

        if new_model_type == "balanced" and not self._has_gpu:
            raise ValueError(
                "Balanced (8B) model requires an NVIDIA GPU for responsive performance."
            )

        if self._ready and self._model_type == new_model_type:
            logger.info("Model %s is already active.", new_model_type)
            return

        logger.info(
            "Switching model from %s to %s...", self._model_type, new_model_type
        )
        self.stop()
        self._model_type = new_model_type
        self.start(force_restart=True)
        logger.info("Switched model to %s successfully.", new_model_type)

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = settings.LLM_MAX_TOKENS,
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

        inference_start_time = time.time()
        llm_output_logger.debug(f"Input messages: \n{json.dumps(messages, indent=4)}")

        response = requests.post(
            f"{self._base_url}/v1/chat/completions",
            json=payload,
            timeout=120,
        )
        logger.info(f"llama-cpp server chat response time: "
                    f"{time.time() - inference_start_time:.2f} seconds")

        response.raise_for_status()
        data = response.json()

        if "usage" in data:
            usage_data = dict(data["usage"])
            if "timings" in data:
                usage_data["timings"] = data["timings"]
            llm_output_logger.debug(f"Token usage: \n{json.dumps(usage_data, indent=4)}")

        msg = data["choices"][0]["message"]
        content = msg.get("content") or ""
        if not content and msg.get("reasoning_content"):
            logger.warning("Assistant response content was empty; falling back to reasoning_content")
            content = msg["reasoning_content"]
        content = skip_thinking_part_response(content)
        llm_output_logger.debug(f"Final response: \n{content}")
        return content

    def chat_with_tools_details(
        self,
        messages: list[dict],
        *,
        max_tokens: int = settings.LLM_MAX_TOKENS,
        temperature: float = 0.7,
        stop: Optional[list[str]] = None,
        tools: Optional[list[dict]] = None,
    ) -> dict:
        """
        Executes multi-turn tool-calling loop and returns a dict:
        {
            "reply": str,
            "tools_called": list[dict],
            "latency_seconds": float
        }
        """
        self._assert_ready()

        messages = list(messages)
        tools = tools or TOOLS
        tools_called: list[dict] = []

        agent_run_start_time = time.time()

        while True:
            payload = {
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "tools": tools,
            }

            if stop:
                payload["stop"] = stop

            inference_start_time = time.time()
            llm_output_logger.debug(f"Input messages: \n{json.dumps(messages, indent=4)}")

            response = requests.post(
                f"{self._base_url}/v1/chat/completions",
                json=payload,
                timeout=120,
            )

            logger.info(
                f"llama-cpp server response time: "
                f"{time.time() - inference_start_time:.2f} seconds"
            )

            if not response.ok:
                logger.error(
                    f"llama-cpp server returned error [{response.status_code}]: {response.text}"
                )
            response.raise_for_status()

            data = response.json()

            if "usage" in data:
                usage_data = dict(data["usage"])
                if "timings" in data:
                    usage_data["timings"] = data["timings"]
                llm_output_logger.debug(f"Token usage: \n{json.dumps(usage_data, indent=4)}")

            message = data["choices"][0]["message"]

            # No tool call → final answer
            if not message.get("tool_calls"):
                latency_seconds = round(time.time() - agent_run_start_time, 2)
                logger.info(f"Agent total run time: {latency_seconds:.2f} seconds")
                content = message.get("content") or ""
                if not content and message.get("reasoning_content"):
                    logger.warning("Assistant response content was empty; falling back to reasoning_content")
                    content = message["reasoning_content"]
                final_response = skip_thinking_part_response(content)
                llm_output_logger.debug(f"Final response: \n{final_response}")
                return {
                    "reply": final_response,
                    "tools_called": tools_called,
                    "latency_seconds": latency_seconds,
                }

            # Add assistant message containing tool call
            messages.append(message)

            # Execute requested tools
            for tool_call in message["tool_calls"]:
                function_name = tool_call["function"]["name"]
                raw_args = tool_call["function"]["arguments"]
                arguments = (
                    json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                )

                if function_name not in TOOL_FUNCTIONS:
                    raise ValueError(
                        f"Unknown tool requested: {function_name}"
                    )

                tools_called.append({
                    "name": function_name,
                    "arguments": arguments,
                })

                function = TOOL_FUNCTIONS[function_name]
                result = function(**arguments)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", ""),
                    "content": json.dumps(result),
                })

    def chat_with_tools(
        self,
        messages: list[dict],
        *,
        max_tokens: int = settings.LLM_MAX_TOKENS,
        temperature: float = 0.7,
        stop: Optional[list[str]] = None,
        tools: Optional[list[dict]] = None,
    ) -> str:
        """Backward-compatible method returning only the final answer string."""
        res = self.chat_with_tools_details(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop,
            tools=tools,
        )
        return res["reply"]

    def chat_with_tools_stream(
        self,
        messages: list[dict],
        *,
        max_tokens: int = settings.LLM_MAX_TOKENS,
        temperature: float = 0.7,
        stop: Optional[list[str]] = None,
        tools: Optional[list[dict]] = None,
    ):
        """
        Yields generator event dicts during tool execution and response streaming:
        - {"event": "tool_call", "data": {"name": ..., "arguments": ...}}
        - {"event": "tool_result", "data": {"name": ..., "count": ...}}
        - {"event": "token", "data": {"text": ...}}
        - {"event": "done", "data": {"reply": ..., "tools_called": ..., "latency_seconds": ...}}
        """
        self._assert_ready()

        messages = list(messages)
        tools = tools or TOOLS
        tools_called: list[dict] = []
        agent_run_start_time = time.time()

        while True:
            payload = {
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "tools": tools,
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
            message = data["choices"][0]["message"]

            if not message.get("tool_calls"):
                latency_seconds = round(time.time() - agent_run_start_time, 2)
                content = message.get("content") or ""
                if not content and message.get("reasoning_content"):
                    content = message["reasoning_content"]
                final_response = skip_thinking_part_response(content)

                words = re.findall(r"\S+|\s+", final_response)
                for w in words:
                    yield {"event": "token", "data": {"text": w, "content": w}}
                    time.sleep(0.01)

                yield {
                    "event": "done",
                    "data": {
                        "reply": final_response,
                        "tools_called": tools_called,
                        "latency_seconds": latency_seconds,
                    },
                }
                return

            messages.append(message)

            for tool_call in message["tool_calls"]:
                function_name = tool_call["function"]["name"]
                raw_args = tool_call["function"]["arguments"]
                arguments = (
                    json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                )

                if function_name not in TOOL_FUNCTIONS:
                    raise ValueError(f"Unknown tool requested: {function_name}")

                tools_called.append({
                    "name": function_name,
                    "arguments": arguments,
                })

                yield {
                    "event": "tool_call",
                    "data": {
                        "name": function_name,
                        "arguments": arguments,
                    },
                }

                function = TOOL_FUNCTIONS[function_name]
                result = function(**arguments)

                count = len(result) if isinstance(result, list) else 1
                yield {
                    "event": "tool_result",
                    "data": {
                        "name": function_name,
                        "count": count,
                    },
                }

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", ""),
                    "content": json.dumps(result),
                })

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
# if __name__ == "__main__":
#     from storage import Database
#     from sync import GmailSync
#     from .tools import init_tools
#     from .system_prompt import get_system_prompt

#     db = Database(
#         store_dir=settings.DB_STORE_DIR,
#         sqlite_filename=settings.DB_SQLITE_FILENAME,
#         search_email_fields=settings.SEARCH_EMAIL_FIELDS,
#         email_thread_fields=settings.EMAIL_THREAD_FIELDS,
#     )

#     gmail_sync = GmailSync(db)

#     init_tools(db, gmail_sync)

#     llm = LLM()

#     llm.setup()
#     llm.start()

#     try:
#         reply = llm.chat_with_tools([
#             {"role": "system", "content": get_system_prompt()},
#             {"role": "user", "content": "Summarise my conversations with Noel from past 1 week."},
#         ])
#         print("[chat_with_tools] response:", reply)
#     finally:
#         llm.stop()
