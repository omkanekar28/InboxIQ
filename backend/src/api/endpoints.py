import os
import json
import uuid
import time
import threading
from pathlib import Path
from typing import Optional, Any

from fastapi import APIRouter, HTTPException, UploadFile, File, Request, status
from fastapi.responses import StreamingResponse

from settings import settings
from storage.database import Database
from sync.gmail_sync import GmailSync
from agent.tools import init_tools
from agent.llm import LLM
from agent.system_prompt import get_system_prompt
from bootstrap.setup_llm_server import get_gpu_info
from utils import get_logger

from api.models import (
    ChatRequest,
    ChatResponse,
    ToolCallInfo,
    SyncTriggerResponse,
    SyncStatusResponse,
    HardwareResponse,
    ModelSwitchRequest,
    ModelSwitchResponse,
    SetupStatusResponse,
    CredentialsUploadResponse,
    AuthResponse,
)

logger = get_logger(__name__)

router = APIRouter()

# Application singletons
db: Optional[Database] = None
gmail_sync: Optional[GmailSync] = None
llm: Optional[LLM] = None

# Background sync job tracking
sync_job_lock = threading.Lock()
sync_job_state: dict[str, Any] = {
    "job_id": None,
    "running": False,
    "status": "idle",
    "error": None,
    "current_synced": 0,
    "total_to_sync": 0,
    "percent": 0.0,
}

# Startup progress tracking
startup_lock = threading.Lock()
startup_state: dict[str, Any] = {
    "completed": False,
    "current_step": "init",
    "message": "Initializing InboxIQ services...",
    "steps": [
        {"id": "database", "label": "SQLite Database & Local Stores", "status": "pending", "message": "Waiting...", "progress": None},
        {"id": "models", "label": "Liquid AI Models (GGUF)", "status": "pending", "message": "Waiting...", "progress": None},
        {"id": "runtime", "label": "llama.cpp Hardware Engine", "status": "pending", "message": "Waiting...", "progress": None},
        {"id": "server", "label": "Local LLM Server Runtime", "status": "pending", "message": "Waiting...", "progress": None},
    ],
    "error": None,
}


def _format_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    elif num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    elif num_bytes < 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{num_bytes / (1024 * 1024 * 1024):.2f} GB"


def _format_speed(speed_bytes_sec: float) -> str:
    if speed_bytes_sec <= 0:
        return ""
    if speed_bytes_sec < 1024 * 1024:
        return f"{speed_bytes_sec / 1024:.1f} KB/s"
    return f"{speed_bytes_sec / (1024 * 1024):.1f} MB/s"


def update_startup_step(
    step_id: str,
    status_val: str,
    message: Optional[str] = None,
    progress: Optional[dict] = None,
):
    with startup_lock:
        startup_state["current_step"] = step_id
        if message:
            startup_state["message"] = message
        for step in startup_state["steps"]:
            if step["id"] == step_id:
                step["status"] = status_val
                if message:
                    step["message"] = message
                if progress is not None:
                    step["progress"] = progress
                elif status_val == "completed":
                    if step.get("progress"):
                        step["progress"]["percent"] = 100
                break


def _init_heavy_services_worker():
    global llm
    logger.info("Starting background setup for models, runtime, and LLM server...")

    # Step 2: Models
    try:
        update_startup_step("models", "in_progress", "Checking and verifying AI models...")

        def _on_model_progress(data: dict):
            downloaded = data.get("downloaded", 0)
            total = data.get("total", 0)
            speed = data.get("speed", 0.0)
            m_num = data.get("model_num", 1)
            m_total = data.get("total_models", 2)
            m_type = data.get("model_type", "")
            m_name = data.get("filename", "")

            pct = round((downloaded / total * 100), 1) if total > 0 else 0
            d_str = _format_size(downloaded)
            t_str = _format_size(total) if total > 0 else "..."
            sp_str = _format_speed(speed)

            msg = f"Downloading {m_type} ({m_num}/{m_total}): {d_str} / {t_str}"
            if sp_str:
                msg += f" • {sp_str}"

            progress_info = {
                "percent": pct,
                "downloaded_bytes": downloaded,
                "total_bytes": total,
                "downloaded_str": d_str,
                "total_str": t_str,
                "speed_str": sp_str,
                "detail": f"{m_name} ({m_num}/{m_total})",
            }
            update_startup_step("models", "in_progress", msg, progress=progress_info)

        from bootstrap.setup_models import setup_models
        setup_models(
            balanced_model_url=settings.MODEL_DOWNLOAD_URL_BALANCED,
            lightweight_model_url=settings.MODEL_DOWNLOAD_URL_LIGHTWEIGHT,
            models_store_dir=settings.MODEL_STORE_DIR,
            progress_callback=_on_model_progress,
        )
        update_startup_step("models", "completed", "AI models verified and ready.", progress={"percent": 100})
    except Exception as e:
        logger.error(f"Error verifying models: {e}")
        with startup_lock:
            startup_state["error"] = f"Model verification error: {e}"
        update_startup_step("models", "failed", str(e))
        return

    # Step 3: Runtime
    try:
        update_startup_step("runtime", "in_progress", "Checking llama.cpp runtime and GPU acceleration...")
        from bootstrap.setup_llm_server import install_llama_runtime, is_gpu_available
        gpu_avail = is_gpu_available()
        binaries_url = (
            settings.LLAMA_CPP_CUDA_BINARIES_URL
            if gpu_avail
            else settings.LLAMA_CPP_CPU_BINARIES_URL
        )

        def _on_runtime_progress(downloaded, total, speed=0.0, status="downloading"):
            pct = round((downloaded / total * 100), 1) if total > 0 else 0
            d_str = _format_size(downloaded)
            t_str = _format_size(total) if total > 0 else "..."
            sp_str = _format_speed(speed)

            if status == "extracting":
                msg = "Extracting llama.cpp runtime archive..."
                p_info = {
                    "percent": 100,
                    "downloaded_bytes": total,
                    "total_bytes": total,
                    "downloaded_str": t_str,
                    "total_str": t_str,
                    "speed_str": "",
                    "detail": "Extracting runtime...",
                }
            elif status == "installed":
                msg = "llama.cpp runtime verified."
                p_info = {
                    "percent": 100,
                    "downloaded_bytes": total,
                    "total_bytes": total,
                    "downloaded_str": t_str,
                    "total_str": t_str,
                    "speed_str": "",
                    "detail": "Installed",
                }
            else:
                msg = f"Downloading llama.cpp runtime: {d_str} / {t_str}"
                if sp_str:
                    msg += f" • {sp_str}"
                p_info = {
                    "percent": pct,
                    "downloaded_bytes": downloaded,
                    "total_bytes": total,
                    "downloaded_str": d_str,
                    "total_str": t_str,
                    "speed_str": sp_str,
                    "detail": "llama.cpp runtime binaries",
                }
            update_startup_step("runtime", "in_progress", msg, progress=p_info)

        install_llama_runtime(
            url=binaries_url,
            extract_dir=settings.LLAMA_CPP_BINARIES_STORE_DIR,
            progress_callback=_on_runtime_progress,
            show_progress=False,
        )
        accel_desc = "CUDA GPU Acceleration" if gpu_avail else "CPU Multi-Threading"
        update_startup_step("runtime", "completed", f"llama.cpp engine ready ({accel_desc}).", progress={"percent": 100})
    except Exception as e:
        logger.error(f"Error installing llama runtime: {e}")
        with startup_lock:
            startup_state["error"] = f"Runtime error: {e}"
        update_startup_step("runtime", "failed", str(e))
        return

    # Step 4: Local LLM Server
    try:
        update_startup_step("server", "in_progress", "Launching llama-server and loading model weights into VRAM...")
        llm = LLM(model_type=settings.MODEL_TYPE)
        llm.start()
        update_startup_step("server", "completed", "LLM server active and healthy on port 8001.")
    except Exception as e:
        logger.error(f"Error starting LLM server: {e}")
        with startup_lock:
            startup_state["error"] = f"Server launch error: {e}"
        update_startup_step("server", "failed", str(e))
        return

    with startup_lock:
        startup_state["completed"] = True
        startup_state["current_step"] = "ready"
        startup_state["message"] = "All InboxIQ services are fully initialized!"
        startup_state["error"] = None
    logger.info("InboxIQ background initialization completed successfully.")


def init_services() -> None:
    """Initialize lightweight database services immediately, then spawn background thread for heavy LLM setup."""
    global db, gmail_sync
    logger.info("Initializing InboxIQ backend services...")

    # Step 1: Initialize Database & Sync (fast, ~15ms)
    try:
        update_startup_step("database", "in_progress", "Initializing SQLite database & stores...")
        db = Database(
            store_dir=settings.DB_STORE_DIR,
            sqlite_filename=settings.DB_SQLITE_FILENAME,
            search_email_fields=settings.SEARCH_EMAIL_FIELDS,
            email_thread_fields=settings.EMAIL_THREAD_FIELDS,
        )
        gmail_sync = GmailSync(db=db, auto_auth=True)
        init_tools(db=db, gmail_sync=gmail_sync)
        update_startup_step("database", "completed", "Database ready and schema verified.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        with startup_lock:
            startup_state["error"] = f"Database error: {e}"
        update_startup_step("database", "failed", str(e))
        return

    # Spawn background thread for heavy tasks (models, runtime, LLM server)
    t = threading.Thread(target=_init_heavy_services_worker, daemon=True)
    t.start()


def shutdown_services() -> None:
    """Terminate running server processes on application shutdown."""
    global llm
    logger.info("Shutting down InboxIQ backend services...")
    if llm:
        try:
            llm.stop()
        except Exception as e:
            logger.error(f"Error stopping LLM server: {e}")


# ---------------------------------------------------------
# Health Check
# ---------------------------------------------------------
@router.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "llm_ready": llm.is_ready if llm else False,
        "active_model": llm.model_type if llm else settings.MODEL_TYPE,
    }


@router.get("/api/system/startup")
def get_startup_status():
    with startup_lock:
        return dict(startup_state)


# ---------------------------------------------------------
# Chat Endpoints
# ---------------------------------------------------------
@router.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not llm or not llm.is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM server is not ready. Please check /api/health.",
        )

    formatted_messages = [m.model_dump() for m in req.messages]
    if not any(m.get("role") == "system" for m in formatted_messages):
        formatted_messages.insert(0, {"role": "system", "content": get_system_prompt()})

    if req.stream:
        def event_generator():
            try:
                for chunk in llm.chat_with_tools_stream(formatted_messages):
                    event_type = chunk["event"]
                    data_str = json.dumps(chunk["data"])
                    yield f"event: {event_type}\ndata: {data_str}\n\n"
            except Exception as e:
                logger.error(f"Streaming error in /api/chat: {e}")
                err_data = json.dumps({"error": str(e)})
                yield f"event: error\ndata: {err_data}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        try:
            details = llm.chat_with_tools_details(formatted_messages)
            return ChatResponse(
                reply=details["reply"],
                tools_called=[
                    ToolCallInfo(name=tc["name"], arguments=tc["arguments"])
                    for tc in details.get("tools_called", [])
                ],
                latency_seconds=details["latency_seconds"],
            )
        except Exception as e:
            logger.error(f"Error in /api/chat: {e}")
            raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Sync Endpoints
# ---------------------------------------------------------
def _run_background_sync(job_id: str):
    global sync_job_state

    def _sync_progress_callback(current: int, total: int):
        with sync_job_lock:
            sync_job_state["current_synced"] = current
            sync_job_state["total_to_sync"] = total
            sync_job_state["percent"] = round((current / total) * 100, 1) if total > 0 else 0.0

    try:
        logger.info(f"Starting background sync job {job_id}...")
        if not gmail_sync:
            raise RuntimeError("GmailSync is not initialized.")
        gmail_sync.sync_emails(
            max_recent_emails=settings.GMAIL_SYNC_MAX_RECENT_EMAILS,
            metadata_headers=settings.GMAIL_SYNC_METADATA_HEADERS,
            batch_size=settings.GMAIL_SYNC_BATCH_SIZE,
            progress_callback=_sync_progress_callback,
        )
        with sync_job_lock:
            sync_job_state["status"] = "completed"
            sync_job_state["running"] = False
            sync_job_state["error"] = None
            if sync_job_state["total_to_sync"] > 0:
                sync_job_state["current_synced"] = sync_job_state["total_to_sync"]
                sync_job_state["percent"] = 100.0
        logger.info(f"Background sync job {job_id} completed successfully.")
    except Exception as e:
        logger.error(f"Background sync job {job_id} failed: {e}")
        with sync_job_lock:
            sync_job_state["status"] = "failed"
            sync_job_state["running"] = False
            sync_job_state["error"] = str(e)


@router.post("/api/sync", response_model=SyncTriggerResponse)
def trigger_sync():
    if not gmail_sync or not gmail_sync.is_authenticated():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Gmail account is not authenticated. Please complete OAuth setup first.",
        )

    with sync_job_lock:
        if sync_job_state["running"]:
            return SyncTriggerResponse(
                job_id=sync_job_state["job_id"] or "",
                status="running",
                message="A sync job is already in progress.",
            )

        job_id = str(uuid.uuid4())[:8]
        sync_job_state["job_id"] = job_id
        sync_job_state["running"] = True
        sync_job_state["status"] = "running"
        sync_job_state["error"] = None
        sync_job_state["current_synced"] = 0
        sync_job_state["total_to_sync"] = 0
        sync_job_state["percent"] = 0.0

    t = threading.Thread(target=_run_background_sync, args=(job_id,), daemon=True)
    t.start()

    return SyncTriggerResponse(
        job_id=job_id,
        status="started",
        message="Gmail sync initiated in the background.",
    )


@router.get("/api/sync/status", response_model=SyncStatusResponse)
def get_sync_status():
    last_sync_at = db.get_sync_state("last_sync_at") if db else None
    total_emails = db.get_total_emails() if db else 0

    with sync_job_lock:
        state = sync_job_state["status"]
        running = sync_job_state["running"]
        last_error = sync_job_state["error"]
        current_synced = sync_job_state.get("current_synced", 0)
        total_to_sync = sync_job_state.get("total_to_sync", 0)
        percent = sync_job_state.get("percent", 0.0)

    return SyncStatusResponse(
        state=state,
        last_sync_at=last_sync_at,
        total_emails=total_emails,
        job_running=running,
        last_error=last_error,
        current_synced=current_synced,
        total_to_sync=total_to_sync,
        percent=percent,
    )


# ---------------------------------------------------------
# System & Hardware Endpoints
# ---------------------------------------------------------
@router.get("/api/system/hardware", response_model=HardwareResponse)
def get_hardware_profile():
    gpu_info = get_gpu_info()
    active_model = llm.model_type if llm else settings.MODEL_TYPE
    return HardwareResponse(
        gpu_available=gpu_info["gpu_available"],
        gpu_name=gpu_info["gpu_name"],
        vram_mb=gpu_info["vram_mb"],
        active_model=active_model,
    )


@router.post("/api/system/model", response_model=ModelSwitchResponse)
def switch_model(payload: ModelSwitchRequest):
    if not llm:
        raise HTTPException(status_code=500, detail="LLM service is not initialized.")

    try:
        llm.switch_model(payload.model)
        return ModelSwitchResponse(
            active_model=llm.model_type,
            status="success",
            message=f"Model switched to {payload.model} successfully.",
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error switching model: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to switch model: {e}")


# ---------------------------------------------------------
# Setup & Onboarding Wizard Endpoints
# ---------------------------------------------------------
@router.get("/api/setup/status", response_model=SetupStatusResponse)
def get_setup_status():
    cred_path = Path(settings.GMAIL_SYNC_CREDENTIALS_FILEPATH)
    credentials_ok = False
    if cred_path.exists():
        try:
            with open(cred_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                credentials_ok = "installed" in data or "web" in data
        except Exception:
            credentials_ok = False

    authenticated = gmail_sync.is_authenticated() if gmail_sync else False

    lightweight_filename = settings.MODEL_DOWNLOAD_URL_LIGHTWEIGHT.split("/")[-1].split("?")[0]
    lightweight_path = Path(settings.MODEL_STORE_DIR) / lightweight_filename
    models_downloaded = lightweight_path.exists()

    initial_sync_done = False
    if db:
        initial_sync_done = db.get_sync_state("gmail_last_history_id") is not None

    return SetupStatusResponse(
        credentials_ok=credentials_ok,
        authenticated=authenticated,
        models_downloaded=models_downloaded,
        initial_sync_done=initial_sync_done,
    )


@router.post("/api/setup/credentials", response_model=CredentialsUploadResponse)
async def upload_credentials(
    request: Request,
    file: Optional[UploadFile] = File(None),
):
    dest_path = Path(settings.GMAIL_SYNC_CREDENTIALS_FILEPATH)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    content_bytes = None
    if file is not None:
        content_bytes = await file.read()
    elif request is not None:
        try:
            body = await request.body()
            if body:
                content_bytes = body
        except Exception:
            pass

    if not content_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No credentials file or JSON content provided.",
        )

    try:
        creds_json = json.loads(content_bytes.decode("utf-8"))
        if "installed" not in creds_json and "web" not in creds_json:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Google OAuth credentials format (missing 'installed' or 'web' key).",
            )
        with open(dest_path, "w", encoding="utf-8") as f:
            json.dump(creds_json, f, indent=2)
        return CredentialsUploadResponse(
            status="success",
            message=f"Credentials saved successfully to {dest_path.name}.",
        )
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provided content is not valid JSON.",
        )


@router.post("/api/setup/auth", response_model=AuthResponse)
def trigger_auth():
    if not gmail_sync:
        raise HTTPException(status_code=500, detail="GmailSync service is not initialized.")

    cred_path = Path(settings.GMAIL_SYNC_CREDENTIALS_FILEPATH)
    if not cred_path.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="credentials.json not found. Please upload credentials first.",
        )

    try:
        gmail_sync.authenticate_flow()
        if db:
            init_tools(db=db, gmail_sync=gmail_sync)
        return AuthResponse(
            status="success",
            message="Google OAuth authentication successful.",
        )
    except Exception as e:
        logger.error(f"OAuth flow failed: {e}")
        raise HTTPException(status_code=500, detail=f"Authentication failed: {e}")


def shutdown_services():
    """Cleanly shut down background services and subprocesses."""
    global llm
    logger.info("Shutting down InboxIQ services...")
    if llm:
        try:
            llm.stop()
            logger.info("LLM server stopped cleanly.")
        except Exception as e:
            logger.warning(f"Error stopping LLM during shutdown: {e}")

