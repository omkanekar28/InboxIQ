# InboxIQ 📬

> **A local, privacy-first Gmail AI assistant powered by `llama.cpp` and local small language models (Liquid AI LFM2.5).**  
> Query your inbox in natural language, summarize email threads, and find past conversations without sending a single byte of your data to the cloud.

---

## Overview

InboxIQ runs entirely on your local machine with automatic **GPU acceleration** (NVIDIA CUDA) and seamless **CPU fallback**. It indexes email metadata into a local SQLite database, communicates with Gmail using read-only OAuth2 scopes, and uses a native tool-calling agent loop via `llama-server.exe` to answer queries with deterministic, hallucination-free grounding.

---

## Key Features

- 🔒 **100% Local & Private**: No data leaves your machine. No external cloud LLM tokens or API subscriptions required.
- ⚡ **Hardware-Adaptive**: Automatically detects NVIDIA GPUs via CUDA driver hooks and offloads layers (`-ngl -1`), or falls back to multi-threaded CPU inference.
- 🧠 **Dual-Model Architecture**:
  - **Balanced**: `LFM2.5-8B-A1B-Q4_K_M` — Hybrid MoE model for deep multi-turn reasoning and synthesis.
  - **Lightweight**: `LFM2.5-2.6B-Q4_K_M` — Ultra-fast, memory-efficient local model with strong native tool calling.
- 🎯 **Zero-Bloat Orchestration**: Built directly on native OpenAI-compatible tool calling exposed by `llama-server`. Eliminates heavy graph frameworks (like LangGraph) and query classification layers.
- 🔄 **Efficient Smart Sync**: Full metadata backfill with incremental sync using Gmail `historyId`. Message bodies are fetched and cached on-demand when threads are inspected, saving bandwidth and disk space.
- 🔌 **FastAPI Backend with SSE Streaming**: Token-by-token streaming response, background sync worker with status tracking, hardware profiling, and live model toggling.

---

## Tech Stack

| Layer | Choice | Details & Rationale |
|---|---|---|
| **LLM Models** | **Liquid AI LFM2.5** (GGUF Q4_K_M) | `8B-A1B` (balanced, high-capacity hybrid) or `2.6B` (lightweight, rapid iteration) |
| **LLM Runtime** | **llama.cpp** (`llama-server.exe`, b11050) | Prebuilt Windows binary; supports CUDA 13.4 with full layer offload (`-ngl -1`) or CPU (`-ngl 0`); 16K context window (`-c 16000`) and 512 batch size (`-b 512`) |
| **Configuration** | **Pydantic Settings** (`pydantic-settings`) | Type-safe settings with environment variable overrides and sensible defaults in `settings.py` |
| **Local Store** | **SQLite** (`database.py`) | Indexes `emails` metadata and caches full thread bodies in `emails_content`, with sanitized text & HTML-entity decoding |
| **Sync & Auth** | **Google OAuth2 (Desktop App Flow)** | Secure PKCE/refresh token auth; full initial backfill + incremental sync using Gmail `historyId` |
| **Agent Orchestration** | **Native Tool-Calling Loop** (`llm.py`) | Direct multi-turn loop via `llama-server` `/v1/chat/completions` with JSON tool schemas, dynamic date-aware system prompt, and reasoning fallback |
| **API Layer** | **FastAPI** (`api/server.py`, `api/endpoints.py`) | Serves chat endpoints with SSE streaming (`/api/chat`), background sync (`/api/sync`), setup wizard (`/api/setup/*`), and hardware management (`/api/system/*`) |
| **UI** | **HTML5 / CSS / ES Modules** (Modern dark theme with green accents) | Desktop-style chat interface, first-boot onboarding wizard, and interactive model toggle |
| **Packaging** | **PyInstaller / Nuitka** (Planned) | Bundles backend, static frontend, and `llama.cpp` runtime into a native installer |

---

## Architecture & How It Works

### Native Tool-Calling Loop

Rather than using complex graph engines or artificial query classifiers, InboxIQ uses the native tool-calling capabilities of `llama-server.exe` paired with a focused, date-aware system prompt:

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

### Data Sync & Caching

Implemented in `backend/src/sync/gmail_sync.py`:

1. **Initial Sync (First Boot)**:
   - Authenticates via OAuth2 (`credentials.json` &rarr; `token.json`).
   - Paginates messages via Gmail API (`users.messages.list`).
   - Extracts metadata: `id`, `thread_id`, `sender`, `recipient`, `subject`, `snippet`, `labels`, `date`, and `internal_date_ms`.
   - Batch inserts records into SQLite `emails` table.
   - Records the latest `historyId` in the `sync_state` table.
2. **Incremental Sync (Subsequent Runs)**:
   - Queries `users.history.list` starting from stored `historyId`.
   - Captures added messages, label updates, and message deletions transactionally.
3. **On-Demand Body Fetching**:
   - Message bodies are **not** downloaded in bulk during initial sync.
   - When a thread is inspected via `get_email_thread()`, bodies are fetched from Gmail and cached locally in `emails_content` for instant subsequent access.
4. **Data Sanitization**:
   - Email snippets and bodies are sanitized to strip zero-width joiners (`\u200c`), unescape HTML entities (`&#39;` &rarr; `'`), and normalize whitespace to optimize context window efficiency.

---

## Agent Tool Specifications

Tools exposed to the agent in `backend/src/agent/tools.py`:

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

## Repository Structure

```
InboxIQ/
├── backend/
│   ├── src/
│   │   ├── agent/
│   │   │   ├── llm.py                 # Llama-cpp lifecycle, OpenAI client, tool-calling loop
│   │   │   ├── system_prompt.py       # Dynamic date-aware agent system prompt
│   │   │   └── tools.py               # search_emails & get_email_thread interfaces
│   │   ├── api/
│   │   │   ├── server.py              # FastAPI app setup, lifespan & CORS
│   │   │   ├── endpoints.py           # All API routes (chat, sync, setup, system/models)
│   │   │   └── models/                # Pydantic request & response schemas
│   │   ├── bootstrap/
│   │   │   ├── setup_models.py        # GGUF model auto-downloader & verifier
│   │   │   └── setup_llm_server.py    # GPU detection (CUDA ctypes/smi) & llama.cpp runner
│   │   ├── storage/
│   │   │   └── database.py            # SQLite schema, indexes, transaction decorator
│   │   ├── sync/
│   │   │   └── gmail_sync.py          # OAuth2 flow, full sync, history sync, body caching
│   │   ├── utils/
│   │   │   ├── datetime_functions.py  # RFC 2822 / ISO date parser
│   │   │   ├── file_utils.py          # Streaming file downloader with progress bar
│   │   │   ├── llm_utils.py           # Thinking tags & code fence normalizer
│   │   │   └── logging_setup.py       # Central logging setup
│   │   ├── settings.py                # Central Pydantic BaseSettings
│   │   └── main.py                    # Server entry point with uvicorn & auto-reload
│   ├── scripts/
│   │   └── sqlite_summary.py          # Dev utility to inspect DB table counts & schema
│   ├── tests/
│   │   ├── fixtures/
│   │   │   └── mock_data.py           # 30 mock emails for isolated testing
│   │   ├── agent/
│   │   │   ├── test_tools_isolated.py # Unit tests for SQLite tool queries & caching
│   │   │   └── test_agent_e2e.py      # E2E integration tests with live local LLM
│   │   ├── integration/
│   │   │   └── test_api_server.py     # FastAPI endpoint integration tests
│   │   ├── storage/test_sqlite_db.py  # Storage unit tests
│   │   └── sync/test_gmail_sync.py    # Gmail sync & parser unit tests
│   ├── data/                          # [Generated] SQLite database files (inboxiq.db)
│   ├── models/                        # [Generated] Hugging Face GGUF model files
│   ├── llama-cpp/                     # [Generated] llama.cpp server binaries & DLLs
│   └── logs/                          # [Generated] Application runtime & LLM output logs
├── frontend/                          # [In Progress] React / Vite frontend
├── packaging/                         # [Planned] PyInstaller specs & desktop bundlers
├── pyproject.toml                     # Build definition & dependency specifications
├── README.md                          # Project overview & developer guide
└── PROJECT_PLAN.md                    # Roadmap, architecture decisions & milestone tracker
```

---

## Getting Started

### Prerequisites

- Python 3.10+
- An active virtual environment (e.g. `ai_venv`)
- (Optional) NVIDIA GPU with CUDA drivers for optimal inference speed

### Installation

1. **Activate your virtual environment**:
   ```powershell
   # Windows PowerShell example
   C:\Users\Om\virtual_environments\ai_venv\Scripts\Activate.ps1
   ```

2. **Install project dependencies**:
   ```powershell
   pip install -e backend
   ```

3. **Provide Google OAuth Credentials**:
   - Create a Google Cloud Project with the Gmail API enabled.
   - Configure an **OAuth 2.0 Client ID (Desktop Application)**.
   - Download the client configuration as `credentials.json` and place it in `backend/src/credentials.json` (or upload it via the setup wizard).

### Running the Backend

Launch the backend with automatic code reloading:

```powershell
cd backend\src
python main.py
```

The server will automatically:
1. Detect GPU hardware and download `llama.cpp` prebuilt binaries if needed.
2. Verify local GGUF models.
3. Start `llama-server.exe` in the background.
4. Mount the FastAPI API at `http://127.0.0.1:8000`.

### Running Tests

Run the full test suite:

```powershell
# From repo root
pytest backend/tests
```

Or run specific test groups:

```powershell
# API endpoint integration tests
pytest backend/tests/integration/test_api_server.py

# Tool unit tests (isolated SQLite database)
pytest backend/tests/agent/test_tools_isolated.py

# Live end-to-end agent queries (requires running llama-server)
pytest backend/tests/agent/test_agent_e2e.py -s
```

---

## Security & Privacy

- **Read-Only Scopes**: Only `https://www.googleapis.com/auth/gmail.readonly` is requested. InboxIQ cannot send, modify, or delete your emails.
- **Local Persistence**: All indexed headers, snippets, cached thread bodies, and OAuth refresh tokens are stored strictly within the local `backend/data/` directory.
- **Zero Telemetry**: No tracking, metrics, or logs are transmitted off your machine.
