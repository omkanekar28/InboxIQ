# InboxIQ — Project Plan & Engineering Roadmap

> Internal roadmap, architectural decisions, design constraints, and milestone tracking for the InboxIQ local assistant.

---

## 1. Project Goals & Constraints

### Core Goals
- **Local-first & Zero Cloud Costs**: No email content or LLM tokens ever leave the local machine. Zero subscriptions or paid API keys.
- **Hardware-Adaptive Inference**: Automatically detect NVIDIA GPUs via CUDA driver hooks (`-ngl -1`) and fallback smoothly to multi-threaded CPU execution.
- **Dual-Model Strategy**:
  - **Balanced**: `LFM2.5-8B-A1B-Q4_K_M` (Liquid AI hybrid MoE for deep multi-turn reasoning and complex synthesis).
  - **Lightweight**: `LFM2.5-2.6B-Q4_K_M` (ultra-fast, memory-efficient local model with strong native tool calling).
- **Accurate & Grounded**: Answers are strictly backed by deterministic tool execution against indexed local SQLite data, eliminating hallucinations.
- **Zero-Bloat Orchestration**: Built directly on native OpenAI-compatible tool calling exposed by `llama-server.exe`, avoiding heavy graph frameworks (e.g. LangGraph) and redundant query classification layers.
- **Frictionless First-Boot Onboarding**: First-run wizard in the UI for Google OAuth `credentials.json` upload, automated model checks, and initial mailbox sync.

### Non-Goals (Boundaries)
- **Modifying or Sending Emails**: Strictly read-only (`gmail.readonly`). No draft generation, sending, or deleting.
- **Multi-Tenant / Cloud Hosting**: Designed exclusively as a single-user local desktop application.
- **Third-Party Email Providers (e.g. Outlook/IMAP)**: Gmail-only for the core release to maintain zero external cloud dependencies and keep the architecture lean.

---

## 2. Architectural Decisions & Trade-Offs

### 1. Native Tool Calling vs. Heavy Graph Frameworks
- **Decision**: Avoid LangGraph, CrewAI, or multi-agent orchestration frameworks in favor of a direct multi-turn loop against `llama-server.exe` (`/v1/chat/completions`).
- **Rationale**: Modern small models like Liquid AI LFM2.5 natively output JSON tool calls reliably when supplied with standard OpenAI function definitions. Eliminating graph frameworks cuts hundreds of megabytes of dependencies, eliminates graph state overhead, and makes debugging straightforward.

### 2. On-Demand Body Caching vs. Bulk Download
- **Decision**: Index only metadata (headers, snippets, labels, timestamps) during initial backfill and incremental sync. Fetch full email thread bodies on-demand when `get_email_thread()` is invoked.
- **Rationale**: Downloading full bodies for thousands of emails consumes gigabytes of storage, causes excessive API quota consumption, and drastically increases initial setup time. Thread caching provides instant response for repeated inquiries while keeping the local database lean.

### 3. Dynamic Hardware Guard for Model Switching
- **Decision**: Dynamically detect VRAM and GPU capabilities via `nvidia-smi` and direct CUDA driver bindings. If no GPU is available, the UI disables the `Balanced (8B)` option and forces `Lightweight (2.6B)`.
- **Rationale**: Running 8B models on CPU results in sluggish token generation (~2-4 tokens/s) which hurts user experience, whereas 2.6B runs comfortably on CPU at high speeds.

### 4. Background Sync Job Tracking
- **Decision**: Decouple the `/api/sync` trigger from the sync execution using background worker threads and thread-safe job state dictionaries (`idle`, `running`, `completed`, `failed`).
- **Rationale**: Syncing hundreds or thousands of emails can take 10-60 seconds. A non-blocking endpoint with status polling (`/api/sync/status`) prevents HTTP timeouts and allows real-time progress indicators in the UI.

---

## 3. Development & Implementation Roadmap

### Phase 1: Core Foundation (COMPLETED)
- [x] **Settings & Configuration**: Centralized settings via `settings.py` for URLs, ports, context sizes (16,000), batch sizes (512), and max tokens (4,096).
- [x] **Data Access Layer**: SQLite database schema (`emails`, `emails_content`, `sync_state`) with indexed search fields and transaction decorators.
- [x] **Gmail Sync Engine**: OAuth2 desktop authentication, bulk message ingestion, incremental history sync via `historyId`, and on-demand body caching.
- [x] **Model Bootstrap**: Automatic download and verification of GGUF models (`LFM2.5-8B-A1B` and `LFM2.5-2.6B`).
- [x] **Runtime & Hardware Auto-Detection**: Detection of NVIDIA GPUs via direct `ctypes` CUDA driver hooks (`cuInit`/`cuDeviceGetCount`) and `nvidia-smi` fallback; automated download of CUDA 13.4 or CPU `llama.cpp` releases with dynamic `-ngl -1` / `0` parameterization.
- [x] **LLM Client & Process Management**: Background `llama-server.exe` launch, health check polling, OpenAI-compatible `/v1/chat/completions` client, latency tracking, and reasoning content handling.
- [x] **Tool Definitions**: Implemented `search_emails` and `get_email_thread` linked directly to database and sync caching.

### Phase 2: Agent Architecture (COMPLETED)
- [x] **System Prompt (`agent/system_prompt.py`)**: Dynamic system prompt injecting the live current date, anti-hallucination rules, sender-vs-recipient query handling, and drill-down guidelines.
- [x] **Native Tool-Calling Loop (`agent/llm.py`)**: Direct multi-turn execution loop using `llama-server` `/v1/chat/completions` with JSON tool schemas.
- [x] **Response Sanitization (`utils/llm_utils.py`)**: Clean removal of `<think>` reasoning blocks and code block formatting.

### Phase 3: Testing & Verification (COMPLETED)
- [x] **Isolated Mock Dataset (`tests/fixtures/mock_data.py`)**: 30 realistic test emails covering date ranges, senders, interview invitations, Uber receipts, GitHub alerts, and multi-message threads.
- [x] **Tool Unit Tests (`tests/agent/test_tools_isolated.py`)**: 7 passing tests covering keyword search, sender filtering, relative dates, unread labels, and cached body retrieval.
- [x] **End-to-End LLM Agent Tests (`tests/agent/test_agent_e2e.py`)**: 5 passing real-world integration queries executed live against `llama-server.exe`:
  1. Sender + Relative Date filtering (*"Find all emails from Indeed in the past 2 months"*) &rarr; PASS
  2. Deep Thread Inspection & Synthesis (*"What was the final decision in Alice's project update thread?"*) &rarr; PASS
  3. Unread + Recruiter Messages (*"Show me any unread interview invitations or recruiter messages from this week"*) &rarr; PASS
  4. Negative Case / Anti-Hallucination (*"Did I get any receipts or ride summaries from Uber this month?"*) &rarr; PASS
  5. Count / Aggregation over Date Window (*"How many GitHub notifications have I received in the past 7 days?"*) &rarr; PASS

### Phase 4: Local Server & API (COMPLETED)
- [x] **FastAPI Application (`api/server.py` & `api/endpoints.py`)**:
  - `POST /api/chat`: Accepts conversation messages with SSE streaming support (`stream=True`) or standard JSON, returning synthesized response, tool executions, and latency.
  - `POST /api/sync`: Triggers background incremental or full Gmail sync via worker threads with job tracking.
  - `GET /api/sync/status`: Reports sync state, timestamp of last sync, total indexed emails, and live job status.
  - `GET /api/system/hardware`: Returns hardware profile (GPU availability, device name, VRAM, and active model) via `nvidia-smi` hooks.
  - `POST /api/system/model`: Dynamically toggles active model between `lightweight` (`2.6B`) and `balanced` (`8B`) with process PID tracking; rejects `balanced` if no GPU is available.
  - `GET /api/setup/status`: Checks if `credentials.json` exists, user is authenticated (`token.json`), models are downloaded, and initial sync is completed.
  - `POST /api/setup/credentials`: Accepts uploaded `credentials.json` (multipart or JSON body) and validates schema.
  - `POST /api/setup/auth`: Triggers the Google OAuth browser consent flow and binds active session.
  - `GET /api/health`: Server uptime, model readiness, and active model check.
- [x] **CORS Configuration**: Enabled local origin access for Vite/React dev server (`http://localhost:5173`).
- [x] **Automatic Code Reload**: Configured `watchfiles` in `main.py` with excludes for DB, log, and token files.
- [x] **Integration Testing**: 7 integration tests in `backend/tests/integration/test_api_server.py` verifying all routes, mock LLM streaming, and validation.

### Phase 5: Frontend & User Onboarding (COMPLETED)
- [x] **Frontend Architecture & Modern Dark Design System**:
  - [x] Native zero-build Single-Page Application using modern ES Modules, HTML5, and Vanilla CSS tokens.
  - [x] High-contrast dark aesthetic (`#0A0A0A` background, `#00FF41` electric green accents, Inter & JetBrains Mono typography).
  - [x] Custom animations: glowing status emblem, typing indicator dots, message slide-ins, and blinking streaming cursor.
  - [x] Centralized API client (`src/api.js`) and reactive store (`src/store.js`) with automatic health & sync polling.
  - [x] Mounted directly inside FastAPI (`app.mount('/', ...)`) so `python main.py` serves both UI and API at `http://localhost:8000`.
- [x] **First-Boot Setup Screen (Onboarding Wizard)**:
  - [x] Auto-detects unconfigured states via `/api/setup/status` and directs user to `/setup`.
  - [x] **Step 1: Credentials Upload**: Drag-and-drop file dropzone for `credentials.json` with schema validation.
  - [x] **Step 2: Authentication**: "Connect Gmail" button triggering the local OAuth consent flow with live polling.
  - [x] **Step 3: Initial Sync**: Live progress indicator displaying mailbox indexing counter.
  - [x] **Step 4: Completion**: Celebration card with glowing dial and "Start Chatting" button.
- [x] **Main Chat Interface (`/chat`)**:
  - [x] Real-time SSE streaming reader with blinking cursor `▌` and progressive token rendering.
  - [x] Tool execution pills (displaying `search_emails` or `get_email_thread` with JSON arguments).
  - [x] Interactive empty state with suggested query chips and glowing dial.
  - [x] Top bar active model badge, LLM readiness indicator, and manual sync action button with spinner.
- [x] **Settings Page (`/settings`)**:
  - [x] Model switcher between `Lightweight (2.6B)` and `Balanced (8B)`.
  - [x] **Hardware Guard**: Automatically disables the `Balanced` option when `gpu_available == False`, displaying a warning notice.
  - [x] Monospace terminal-style hardware profile readout (GPU name, VRAM, and context window).

### Phase 6: Packaging & Distribution (PLANNED)
- [ ] Package backend and static frontend with PyInstaller or Nuitka.
- [ ] Bundle prebuilt `llama-server` runtime and setup scripts into a standalone executable.
- [ ] Create simple one-click Windows installer/launcher.

---

## 4. Future Extensions & Backlog

- **Multi-Account Switching**: Support multiple Gmail profiles in SQLite with active account toggle.
- **Attachment Search**: Extract text from PDF/DOCX attachments and index metadata.
- **Automated Email Digests**: Background scheduled tasks producing daily or weekly executive summaries.
- **Saved Queries / Shortcuts**: Pinned prompts for frequent inquiries (e.g. "Weekly receipts", "Interviews scheduled").