# InboxIQ 📬

> **A local, privacy-first Gmail AI assistant powered by `llama.cpp` and local small language models (Liquid AI LFM2.5).**  
> Query your inbox in natural language, summarize email threads, and find past conversations without sending a single byte of your data to the cloud.

---

## 🎬 Demo

[![Watch Demo](https://img.shields.io/badge/▶_Watch_Demo-InboxIQ_in_Action_(1m15s)-00C853?style=for-the-badge&logo=googledrive&logoColor=white)](https://drive.google.com/file/d/1mkMdFRH8Qs5mlSxUl6FlFZ1ffE_-iKjs/view?usp=sharing)

> 🎥 **[Watch the 1m 15s Video Demo on Google Drive](https://drive.google.com/file/d/1mkMdFRH8Qs5mlSxUl6FlFZ1ffE_-iKjs/view?usp=sharing)**  
> See InboxIQ in action: local email indexing, natural-language query grounding with `llama-server` native tool calling, and token-by-token streaming with zero cloud dependencies.

---

## Overview

InboxIQ runs entirely on your local machine with automatic **GPU acceleration** (NVIDIA CUDA) and seamless **CPU fallback**. It indexes email metadata into a local SQLite database, communicates with Gmail using read-only OAuth2 scopes, and uses a native tool-calling agent loop via `llama-server.exe` to answer queries with deterministic, hallucination-free grounding.

---

## Key Features

- 🔒 **100% Local & Private**: No data leaves your machine. No external cloud LLM tokens or API subscriptions required.
- ⚡ **Hardware-Adaptive**: Automatically detects NVIDIA GPUs via CUDA driver hooks and offloads layers (`-ngl -1`), or falls back to multi-threaded CPU inference.
- 🧠 **Dual-Model Architecture**:
  - **Balanced (`2.6B`)**: `LFM2.5-2.6B-Q4_K_M` — Recommended for **higher accuracy and deep reasoning** across complex email threads.
  - **Lightweight (`1.2B`)**: `LFM2.5-1.2B-Thinking-Q4_K_M` — Recommended for **maximum speed and low latency** on any CPU or laptop.
- 🎯 **Zero-Bloat Orchestration**: Built directly on native OpenAI-compatible tool calling exposed by `llama-server`. Eliminates heavy graph frameworks (like LangGraph) and query classification layers.
- 🔄 **Efficient Smart Sync**: Indexes the latest 1,000 emails for fast local search, with incremental sync using Gmail `historyId`. Message bodies are fetched and cached on-demand when threads are inspected, saving bandwidth and disk space.
- 🔌 **FastAPI Backend with SSE Streaming**: Token-by-token streaming response, background sync worker with status tracking, hardware profiling, and live model toggling.

---

## Tech Stack

| Layer | Choice | Details & Rationale |
|---|---|---|
| **LLM Models** | **Liquid AI LFM2.5** (GGUF Q4_K_M) | `2.6B` (Balanced: higher accuracy & deep reasoning) or `1.2B-Thinking` (Lightweight: maximum speed & low latency) |
| **LLM Runtime** | **llama.cpp** (`llama-server.exe`, b11050) | Prebuilt Windows binary; supports CUDA 13.4 with full layer offload (`-ngl -1`) or CPU (`-ngl 0`); 16K context window (`-c 16000`) and 512 batch size (`-b 512`) |
| **Configuration** | **Pydantic Settings** (`pydantic-settings`) | Type-safe settings with environment variable overrides and sensible defaults in `settings.py` |
| **Local Store** | **SQLite** (`database.py`) | Indexes `emails` metadata and caches full thread bodies in `emails_content`, with sanitized text & HTML-entity decoding |
| **Sync & Auth** | **Google OAuth2 (Desktop App Flow)** | Secure PKCE/refresh token auth; full initial backfill + incremental sync using Gmail `historyId` |
| **Agent Orchestration** | **Native Tool-Calling Loop** (`llm.py`) | Direct multi-turn loop via `llama-server` `/v1/chat/completions` with JSON tool schemas, dynamic date-aware system prompt, and reasoning fallback |
| **API Layer** | **FastAPI** (`api/server.py`, `api/endpoints.py`) | Serves chat endpoints with SSE streaming (`/api/chat`), background sync (`/api/sync`), setup wizard (`/api/setup/*`), and hardware management (`/api/system/*`) |
| **UI** | **HTML5 / CSS / ES Modules** (Modern dark theme with green accents) | Desktop-style chat interface, first-boot onboarding wizard, and interactive model toggle |
| **Desktop Shell** | **pywebview (Edge WebView2)** | Dedicated native desktop application window with `#0A0A0A` dark theme, system tray integration, and minimize-to-tray lifecycle |
| **Packaging** | **PyInstaller & Inno Setup** (`packaging/`) | Self-contained Windows installer (`InboxIQ-Setup.exe`) and standalone executable with uninstaller data purge option and data isolation |

---

## Architecture & How It Works

### Native Tool-Calling Loop

Rather than using complex graph engines or artificial query classifiers, InboxIQ uses the native tool-calling capabilities of `llama-server.exe` paired with a focused, date-aware system prompt:

```
                    ┌────────────────────────────────────────────────────────┐
 User query ──────► │  System Prompt Injection (`system_prompt.py`)          │
                    │  - Current dynamic date (calculates relative ranges)   │
                    │  - Strict tool-grounding & anti-hallucination rules    │
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
   - Paginates messages via Gmail API (`users.messages.list`) up to the **latest 1,000 emails** (configured by `GMAIL_SYNC_MAX_RECENT_EMAILS`).
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
├── frontend/                          # Modern web app (HTML/CSS/ES Modules) with reactive state & dark aesthetic
├── packaging/                         # PyInstaller spec, Inno Setup config, icons & InboxIQ-Setup.exe
├── pyproject.toml                     # Build definition & dependency specifications
├── README.md                          # Project overview, simple guide & dev guide
└── PROJECT_PLAN.md                    # Roadmap, architecture decisions & milestone tracker
```

---

## 1. Simple Guide — Quick Start (For End Users)

No Python, terminal, or developer setup required! Anyone on Windows can run InboxIQ with a single installer.

> [!IMPORTANT]
> ### ⚠️ One-Time Access Request (Google OAuth Testing Mode)
> Because InboxIQ interacts with Google's Gmail API in **Testing Mode**, Google's security policy requires every user's Gmail address to be manually registered in the project's **Test Users** whitelist before logging in.
> 
> **How to request access:**
> - 📧 **Email**: Send a quick note to **[reiji146@gmail.com](mailto:reiji146@gmail.com?subject=InboxIQ%20Access%20Request&body=Hi%20Om,%20please%20add%20my%20Gmail%20to%20the%20InboxIQ%20authorized%20test%20users%20list:%20%3CYOUR_GMAIL_ADDRESS%3E)** with your Gmail address (Subject: *InboxIQ Access Request*).
> - 🐙 **GitHub**: Or open an issue on the [InboxIQ Issues](https://github.com/omkanekar28/InboxIQ/issues) page.
> 
> Once added (usually very quickly!), you can proceed with the steps below.

### Step 1: Download the Installer
Download **`InboxIQ-Setup.exe`** directly from this repository:
- Located at [`packaging/dist-installer/InboxIQ-Setup.exe`](packaging/dist-installer/InboxIQ-Setup.exe) (or under the GitHub Releases tab).

### Step 2: Install InboxIQ
- Double-click **`InboxIQ-Setup.exe`**.
- Follow the simple setup wizard (no administrator privileges required).
- The installer places an **InboxIQ** shortcut on your Desktop and Start Menu.

### Step 3: Launch and Connect Your Gmail
1. Open **InboxIQ** from your Desktop shortcut or Start Menu.
2. InboxIQ launches directly in its own dedicated, native desktop application window.
3. The initial startup screen will display live download progress bars while setting up the local model and runtime binaries.
4. On the setup screen:
   - **Step 1 (Credentials)**: Pre-configured credentials are automatically detected (**Done ✓**).
   - **Step 2 (Authentication)**: Click **"Connect Gmail Account"** to sign into your Google account and grant read-only inbox access. *(Ensure your email has been whitelisted as described above).*
   - **Step 3 (Initial Sync)**: Click **"Start Indexing"** to sync recent email metadata into your local SQLite store (shows live count & percentage).
   - **Step 4**: Click **"Start Chatting"**!

> [!NOTE]
> ### 📬 Email Indexing Scope (Latest 1,000 Emails)
> To ensure rapid setup, minimal disk usage, and responsive local queries, InboxIQ indexes your **latest 1,000 emails** by default. As a result, queries regarding **very old email conversations** that precede this 1,000-email window cannot be retrieved or answered.

> [!TIP]
> ### 💡 Model Recommendation
> You can switch between models anytime in the in-app **Settings** menu:
> - **Balanced (2.6B)**: Choose this for **higher accuracy and deep reasoning** across complex multi-turn threads (recommended if you have an NVIDIA GPU).
> - **Lightweight (1.2B Thinking)**: Choose this for **maximum speed and responsiveness**, ideal for standard CPUs and everyday hardware.

> **Native Window & System Tray**: Clicking the window's close (`X`) button hides InboxIQ quietly to your Windows taskbar notification tray so your loaded AI model and background indexing remain instantly available without re-loading overhead. Double-click the tray icon anytime to restore the window, or right-click and select **Quit InboxIQ** to completely exit.
> 
> **Clean Uninstallation**: If you uninstall InboxIQ via Windows Settings or Control Panel, the uninstaller will prompt you whether you want to delete all local user data (downloaded AI models, indexed emails, credentials, and logs) or keep them.

---

## 2. Developer Guide — Running from Source & Building

For developers and contributors who want to run the project locally, modify code, or compile their own installer.

### Prerequisites

- Windows 10/11
- Python 3.10+ (tested on Python 3.10 through 3.14)
- A virtual environment (e.g. `C:\Users\Om\virtual_environments\ai_venv`)
- (Optional) NVIDIA GPU with CUDA drivers for GPU-accelerated inference

### 1. Environment Setup

1. **Clone the repository**:
   ```powershell
   git clone https://github.com/omkanekar28/InboxIQ.git
   cd InboxIQ
   ```

2. **Activate your virtual environment**:
   ```powershell
   # Windows PowerShell example
   C:\Users\Om\virtual_environments\ai_venv\Scripts\Activate.ps1
   ```

3. **Install dependencies**:
   ```powershell
   pip install -e backend
   pip install pyinstaller pystray pillow
   ```

4. **OAuth Credentials**:
   Place your Google Cloud OAuth Client credentials file at `backend/src/credentials.json` (or let the app use the bundled `packaging/credentials.json`).

### 2. Running in Development Mode

Run the backend server directly from the repository root:

```powershell
python backend/src/main.py
```

**Development Features:**
- **Auto-Reload**: Code changes in `backend/src/` automatically trigger a server reload.
- **Live Frontend**: Static files are served directly from `frontend/`. Edits to HTML, CSS, or JS reflect immediately upon browser refresh without rebuilding anything.
- **Hardware Profile**: Automatically detects your GPU and configures `-ngl -1` layer offloading or CPU multi-threading.
- **Fast Startup**: Local models in `backend/models` are automatically linked to `%APPDATA%\InboxIQ\models` on first run without re-downloading.

### 3. Running Automated Tests

Run the full pytest suite:

```powershell
# API endpoint integration tests
pytest backend/tests/integration/test_api_server.py -v

# Tool unit tests with isolated SQLite database
pytest backend/tests/agent/test_tools_isolated.py -v

# Gmail sync unit tests
pytest backend/tests/sync/test_gmail_sync.py -v

# Full suite
pytest backend/tests/ -v
```

### 4. Building the Standalone Windows Installer

To package the application into a standalone folder and compile the single-file `InboxIQ-Setup.exe` installer:

```powershell
# Requires Inno Setup 6 (winget install JRSoftware.InnoSetup)
powershell -ExecutionPolicy Bypass -File packaging/build.ps1
```

This automated build script:
1. Validates or generates multi-resolution application icons (`icon.ico` & `icon.png`).
2. Bundles the backend, static frontend, and dependencies with PyInstaller (`packaging/inboxiq.spec`).
3. Compiles the complete installer with Inno Setup into `packaging/dist-installer/InboxIQ-Setup.exe`.

---

## Security & Privacy

- **Read-Only Scopes**: Only `https://www.googleapis.com/auth/gmail.readonly` is requested. InboxIQ cannot send, modify, or delete your emails.
- **Local Persistence**: All indexed headers, snippets, cached thread bodies, and OAuth refresh tokens are stored strictly within the user's local directory (`%APPDATA%\InboxIQ` for the installed app, or `backend/data/` in dev mode).
- **Zero Telemetry**: No tracking, metrics, or logs are transmitted off your machine.
