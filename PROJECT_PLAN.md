# InboxIQ (Local Email Agent)

A local, privacy-first agentic assistant that answers natural-language questions about your Gmail history — e.g. *"Summarize all mails I sent to xyz in the past 3 months"* or *"List all interviews I was invited to this week"* — without sending any data to the cloud.

Runs locally on your machine with automatic **GPU acceleration** (NVIDIA CUDA) and seamless **CPU fallback**, supporting both lightweight and balanced local models. Everything in this stack is free, open source, and runs offline after initial setup.

---

## 1. Goals

- **Local-first**: No data leaves your machine; zero cloud API subscriptions or external LLM tokens required.
- **Hardware-adaptive**: Automatically detects and leverages NVIDIA GPUs (CUDA) via `-ngl -1` offload, or falls back to multi-threaded CPU inference on standard laptops.
- **Dual-model architecture**:
  - **Balanced**: `LFM2.5-8B-A1B-Q4_K_M` (Liquid AI hybrid MoE model for deep multi-turn reasoning and synthesis).
  - **Lightweight**: `LFM2.5-2.6B-Q4_K_M` (ultra-fast, memory-efficient local model with strong native tool-calling).
- **Accurate & Grounded**: Answers are strictly backed by deterministic tool execution against indexed local SQLite data, eliminating hallucinations.
- **Zero-Bloat Orchestration**: Built directly on native OpenAI-compatible tool calling exposed by `llama-server`, eliminating heavy graph frameworks (like LangGraph) and redundant query classification layers.
- **Zero-friction install & First-Run Wizard**: Guided first-boot setup in the UI for Google OAuth `credentials.json`, automated model verification, and initial email sync.

## 2. Non-goals (for now)

- Sending, deleting, or modifying emails (read-only scopes strictly enforced).
- Multi-user or hosted cloud deployment.
- Support for email providers other than Gmail (Outlook integration was evaluated and dropped to maintain zero external cloud dependencies and keep the architecture lean and focused).

---

## 3. Tech Stack

| Layer | Choice | Details & Rationale |
|---|---|---|
| **LLM Models** | **Liquid AI LFM2.5** (GGUF Q4_K_M) | `8B-A1B` (balanced, high-capacity hybrid) or `2.6B` (lightweight, rapid iteration) |
| **LLM Runtime** | **llama.cpp** (`llama-server.exe`, b11050) | Auto-downloads prebuilt Windows binary; supports CUDA 13.4 with full layer offload (`-ngl -1`) or CPU (`-ngl 0`); configured with 16K context window (`-c 16000`) and 512 batch size (`-b 512`) |
| **Configuration** | **Pydantic Settings** (`pydantic-settings`) | Type-safe settings with environment variable overrides and sensible defaults in `settings.py` |
| **Local Store** | **SQLite** (`database.py`) | Indexes `emails` metadata and caches full thread bodies in `emails_content`, with sanitized text & HTML-entity decoding |
| **Sync & Auth** | **Google OAuth2 (Desktop App Flow)** | Secure PKCE/refresh token auth; full initial backfill + incremental sync using Gmail `historyId` |
| **Agent Orchestration** | **Native Tool-Calling Loop** (`llm.py`) | Direct multi-turn loop via `llama-server` `/v1/chat/completions` with JSON tool schemas, dynamic date-aware system prompt, and reasoning fallback |
| **API Layer** | **FastAPI** (Planned) | Serves the agent locally (`/api/chat`, `/api/sync`), setup endpoints (`/api/setup/*`), and hardware/model management (`/api/system/*`) |
| **UI** | **React / Vite** (Planned) | Desktop-style chat interface, first-boot onboarding wizard, and interactive model toggle (Balanced / Lightweight with GPU guard) |
| **Packaging** | **PyInstaller / Nuitka** (Planned) | Bundles backend, static frontend, and `llama.cpp` runtime into a native installer |

---

## 4. Architecture

### Native Tool-Calling Loop (No Heavy Graph Frameworks)

Rather than introducing complex graph engines (e.g. LangGraph) or an artificial rule-based query classifier, InboxIQ uses the native tool-calling capabilities of `llama-server.exe` paired with a focused system prompt. Modern small models (such as Liquid AI LFM2.5 2.6B and 8B) handle function routing, parameter extraction, and multi-turn conversation reliably without multi-node graph overhead.

```
                    ┌────────────────────────────────────────────────────────┐
 User query ──────► │  System Prompt Injection (`system_prompt.py`)          │
                    │  - Current dynamic date (calculates relative ranges)   │
                    │  - Strict tool-grounding & anti-hallucination rules   │
                    │  - Heuristics for sender/keyword/thread disambiguation │
                    └──────────────────────────┬─────────────────────────────┘
                                               │
                                               ▼
                    ┌────────────────────────────────────────────────────────┐
                    │               llama-server HTTP API                    │
                    │            `/v1/chat/completions`                      │
                    │  (Evaluates messages + tools: search_emails,           │
                    │   get_email_thread)                                    │
                    └──────────────────────────┬─────────────────────────────┘
                                               │
                   Does the LLM request one or more tool calls?
                                  /                 \
                             YES /                   \ NO
                                ▼                     ▼
        ┌────────────────────────────────┐     ┌────────────────────────────────┐
        │    Deterministic Execution     │     │     Final Answer Synthesis     │
        │    (`agent/tools.py`)          │     │    (`agent/llm.py`)            │
        │  - search_emails (SQLite)      │     │  - Strip <think> reasoning tags│
        │  - get_email_thread (DB/Gmail) │     │  - Fallback to reasoning if    │
        │  Appends `role: tool` output   │     │    content is empty            │
        └───────────────┬────────────────┘     │  - Return grounded answer      │
                        │                      └────────────────────────────────┘
                        ▼                                      ▲
             (Loop back to llama-server) ──────────────────────┘
```

---

## 5. Data Sync Architecture

Implemented in `sync/gmail_sync.py`:

1. **Initial Sync (First Boot)**:
   - Authenticates via OAuth2 (`token.json` / `credentials.json`).
   - Paginates all messages via Gmail API (`users.messages.list`).
   - Extracts metadata: `id`, `thread_id`, `sender`, `recipient`, `subject`, `snippet`, `labels`, `date`, and `internal_date_ms`.
   - Batch inserts records into the SQLite `emails` table.
   - Records the latest `historyId` in the `sync_state` table.
2. **Incremental Sync (Subsequent Runs)**:
   - Queries `users.history.list` starting from the stored `historyId`.
   - Captures added messages, label updates, and message deletions.
   - Updates the database transactionally.
3. **On-Demand Body Fetching**:
   - Message bodies are **not** downloaded in bulk during initial sync (saving gigabytes of bandwidth and disk).
   - When a thread is queried via `get_email_thread()`, bodies are fetched from Gmail and cached locally in `emails_content` for immediate reuse.
4. **Data Sanitization**:
   - Stored email snippets and cached bodies are sanitized to strip zero-width joiners (`\u200c`), unescape HTML entities (`&#39;` &rarr; `'`), and normalize excess whitespace to optimize prompt context efficiency.

---

## 6. Current Repository Structure

```
InboxIQ/
├── backend/
│   ├── src/
│   │   ├── agent/
│   │   │   ├── __init__.py
│   │   │   ├── llm.py                 # [IMPLEMENTED] Llama-cpp lifecycle, OpenAI-compatible client, chat_with_tools loop
│   │   │   ├── system_prompt.py       # [IMPLEMENTED] Dynamic date-aware agent system prompt
│   │   │   └── tools.py               # [IMPLEMENTED] search_emails & get_email_thread tool interfaces & bindings
│   │   ├── bootstrap/
│   │   │   ├── __init__.py
│   │   │   ├── setup_models.py        # [IMPLEMENTED] Auto-downloader for HuggingFace GGUF models
│   │   │   └── setup_llm_server.py    # [IMPLEMENTED] GPU detector (ctypes/smi), llama.cpp downloader & runner
│   │   ├── storage/
│   │   │   ├── __init__.py
│   │   │   └── database.py            # [IMPLEMENTED] SQLite schema, indexes, transaction decorator, sanitized search queries
│   │   ├── sync/
│   │   │   ├── __init__.py
│   │   │   └── gmail_sync.py          # [IMPLEMENTED] OAuth2 flow, full sync, history sync, body caching
│   │   ├── utils/
│   │   │   ├── __init__.py
│   │   │   ├── datetime_functions.py  # [IMPLEMENTED] RFC 2822 / ISO date parser with IST/UTC handling
│   │   │   ├── file_utils.py          # [IMPLEMENTED] Streaming file downloader with tqdm progress
│   │   │   ├── llm_utils.py           # [IMPLEMENTED] Strip thinking tags & code fence normalizer
│   │   │   └── logging_setup.py       # [IMPLEMENTED] App-wide logging setup
│   │   ├── api/
│   │   │   ├── .gitkeep
│   │   │   └── server.py              # [PLANNED] FastAPI backend (chat, sync, setup, system/models)
│   │   ├── setup_wizard/              # First-run onboarding helpers & status verifier
│   │   ├── eval/                      # Extended benchmark query definitions
│   │   ├── settings.py                # [IMPLEMENTED] Central Pydantic BaseSettings
│   │   └── main.py                    # [IN PROGRESS] Top-level application entry point
│   ├── scripts/
│   │   └── sqlite_summary.py          # [IMPLEMENTED] Developer utility to inspect DB table counts & schema
│   ├── tests/
│   │   ├── fixtures/
│   │   │   ├── __init__.py
│   │   │   └── mock_data.py           # [IMPLEMENTED] 30 realistic mock emails for isolated testing
│   │   ├── agent/
│   │   │   ├── test_tools_isolated.py # [IMPLEMENTED] 7 unit tests verifying SQLite tool queries & caching
│   │   │   └── test_agent_e2e.py      # [IMPLEMENTED] 5 end-to-end integration tests with live local LLM
│   │   ├── storage/test_sqlite_db.py  # Storage unit tests
│   │   └── sync/test_gmail_sync.py    # Gmail sync & parser unit tests
│   ├── data/                          # [GENERATED] SQLite database files (inboxiq.db)
│   ├── models/                        # [GENERATED] Hugging Face GGUF model files
│   ├── llama-cpp/                     # [GENERATED] Extracted llama.cpp server binaries & DLLs
│   └── logs/                          # [GENERATED] Application runtime & LLM output logs
├── frontend/                          # [PLANNED] React frontend application (Chat + First-Boot Wizard)
├── packaging/                         # [PLANNED] PyInstaller specs & desktop bundler scripts
├── pyproject.toml                     # Build definition & dependency specifications
├── README.md
└── PROJECT_PLAN.md
```

---

## 7. Tool Specifications

Tools exposed to the agent in `agent/tools.py`:

```python
def search_emails(
    keyword: str | None = None,     # Case-insensitive substring search in subject or snippet
    sender: str | None = None,      # Partial match against sender address/name
    recipient: str | None = None,   # Partial match against recipient address
    date_from: str | None = None,   # Inclusive lower date bound (parsed flexibly)
    date_to: str | None = None,     # Inclusive upper date bound (parsed flexibly)
    label: str | None = None,       # Gmail label filter (e.g. 'INBOX', 'UNREAD', 'STARRED')
    limit: int = 25,                # Max results returned (ordered newest-first)
) -> list[dict]:
    """Queries indexed email metadata from SQLite; does not load full body text."""

def get_email_thread(
    thread_id: str                  # Gmail thread identifier
) -> list[dict]:
    """Returns all emails in a thread with full body text (fetched & cached locally)."""
```

---

## 8. Development & Implementation Roadmap

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
- [x] **Native Tool-Calling Loop (`agent/llm.py`)**: Direct multi-turn execution loop using `llama-server` `/v1/chat/completions` with JSON tool schemas. No LangGraph or query classification layers needed.
- [x] **Response Sanitization (`utils/llm_utils.py`)**: Clean removal of `<think>` blocks and code block formatting.

### Phase 3: Testing & Verification (COMPLETED)
- [x] **Isolated Mock Dataset (`tests/fixtures/mock_data.py`)**: 30 realistic test emails covering date ranges, senders, interview invitations, Uber receipts, GitHub alerts, and multi-message threads.
- [x] **Tool Unit Tests (`tests/agent/test_tools_isolated.py`)**: 7 passing tests covering keyword search, sender filtering, relative dates, unread labels, and cached body retrieval.
- [x] **End-to-End LLM Agent Tests (`tests/agent/test_agent_e2e.py`)**: 5 passing real-world integration queries executed live against `llama-server.exe`:
  1. Sender + Relative Date filtering (*"Find all emails from Indeed in the past 2 months"*) &rarr; PASS
  2. Deep Thread Inspection & Synthesis (*"What was the final decision in Alice's project update thread?"*) &rarr; PASS
  3. Unread + Recruiter Messages (*"Show me any unread interview invitations or recruiter messages from this week"*) &rarr; PASS
  4. Negative Case / Anti-Hallucination (*"Did I get any receipts or ride summaries from Uber this month?"*) &rarr; PASS
  5. Count / Aggregation over Date Window (*"How many GitHub notifications have I received in the past 7 days?"*) &rarr; PASS

### Phase 4: Local Server & API (NEXT UP)
- [ ] **FastAPI Application (`api/server.py`)**:
  - `POST /api/chat`: Accepts conversation messages and returns the synthesized response, tools called, and latency.
  - `POST /api/sync`: Triggers background incremental or full Gmail sync.
  - `GET /api/sync/status`: Reports sync state, timestamp of last sync, and total indexed emails.
  - `GET /api/system/hardware`: Returns hardware profile (GPU availability, device name, VRAM, and active model).
  - `POST /api/system/model`: Dynamically toggles active model between `lightweight` (`2.6B`) and `balanced` (`8B`). Rejects `balanced` if no GPU is available.
  - `GET /api/setup/status`: Checks if `credentials.json` exists, user is authenticated (`token.json`), models are downloaded, and initial sync is completed.
  - `POST /api/setup/credentials`: Accepts uploaded `credentials.json` or writes file directly.
  - `POST /api/setup/auth`: Triggers the Google OAuth browser consent flow.
  - `GET /api/health`: Basic uptime and server readiness check.
- [ ] **CORS Configuration**: Enable local origin access for the Vite/React dev server (`http://localhost:5173`).

### Phase 5: Frontend & User Onboarding
- [ ] **First-Boot Setup Screen (Onboarding Wizard)**:
  - Automatically displayed on first run if `/api/setup/status` indicates unconfigured state.
  - **Step 1: Credentials Upload**: Drag-and-drop or file selector for `credentials.json`, accompanied by step-by-step instructions for Google Cloud Console OAuth setup.
  - **Step 2: Authentication**: One-click "Connect Gmail" button triggering the local OAuth consent flow.
  - **Step 3: Initial Sync**: Live progress indicator displaying initial mailbox indexing.
  - **Step 4: Completion**: Smooth transition to the primary chat interface once initial sync and models are verified.
- [ ] **Main Chat Interface**:
  - **Header Model Toggle**: Segmented toggle between `Lightweight (2.6B)` and `Balanced (8B)`.
  - **Hardware Guard**: Automatically disables the `Balanced` option when `gpu_available == False`, displaying a tooltip: *"Balanced (8B) requires an NVIDIA GPU for responsive performance. Using Lightweight (2.6B) on CPU."*
  - **Chat Area**: Message stream with clean Markdown rendering, tool invocation badges/chips (showing `search_emails` or `get_email_thread` executions), latency display, and thread inspection modal.
  - **Manual Sync Button**: Status chip showing last sync time with an on-demand "Sync Now" button.

### Phase 6: Packaging & Distribution
- [ ] Package backend and static frontend with PyInstaller or Nuitka.
- [ ] Bundle prebuilt `llama-server` runtime and setup scripts into a standalone executable.

---

## 9. Future Extensions

- Multi-account Gmail switching.
- Attachments metadata indexing and local search.
- Background recurring email digests (e.g. daily executive brief).