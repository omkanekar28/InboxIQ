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
}


def init_services() -> None:
    """Initialize application singletons and start LLM runtime."""
    global db, gmail_sync, llm
    logger.info("Initializing InboxIQ backend services...")

    # 1. Initialize SQLite Database
    db = Database(
        store_dir=settings.DB_STORE_DIR,
        sqlite_filename=settings.DB_SQLITE_FILENAME,
        search_email_fields=settings.SEARCH_EMAIL_FIELDS,
        email_thread_fields=settings.EMAIL_THREAD_FIELDS,
    )

    # 2. Initialize Gmail Sync Client (non-blocking if not yet authenticated)
    gmail_sync = GmailSync(db=db, auto_auth=True)

    # 3. Bind tools to Database and Sync
    init_tools(db=db, gmail_sync=gmail_sync)

    # 4. Initialize and start LLM runtime
    llm = LLM(model_type=settings.MODEL_TYPE)
    try:
        llm.setup()
        logger.info("Starting llama-server on startup...")
        llm.start()
        logger.info("Llama-server started and healthy.")
    except Exception as e:
        logger.error(f"Error starting LLM server during startup: {e}")


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
    try:
        logger.info(f"Starting background sync job {job_id}...")
        if not gmail_sync:
            raise RuntimeError("GmailSync is not initialized.")
        gmail_sync.sync_emails(
            max_recent_emails=settings.GMAIL_SYNC_MAX_RECENT_EMAILS,
            metadata_headers=settings.GMAIL_SYNC_METADATA_HEADERS,
            batch_size=settings.GMAIL_SYNC_BATCH_SIZE,
        )
        with sync_job_lock:
            sync_job_state["status"] = "completed"
            sync_job_state["running"] = False
            sync_job_state["error"] = None
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

    return SyncStatusResponse(
        state=state,
        last_sync_at=last_sync_at,
        total_emails=total_emails,
        job_running=running,
        last_error=last_error,
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
