# InboxIQ (Local Email Agent)

A local, privacy-first agentic assistant that answers natural-language questions about your Gmail history — e.g. *"Summarize all mails I sent to xyz in the past 3 months"* or *"List all interviews I was invited to this year"* — without sending any data to the cloud.

Runs locally on your machine with automatic **GPU acceleration** (NVIDIA CUDA) and seamless **CPU fallback**, supporting both lightweight and balanced local models. Everything in this stack is free, open source, and runs offline after initial setup.

---

## 1. Goals

- **Local-first**: No data leaves your machine; zero cloud API subscriptions or external LLM tokens required.
- **Hardware-adaptive**: Automatically detects and leverages NVIDIA GPUs (CUDA) via `-ngl -1` offload, or falls back to multi-threaded CPU inference on any standard laptop.
- **Dual-model architecture**:
  - **Balanced**: `LFM2.5-2.6B-Q4_K_M` (agentic reasoning, tool calling, 128K context window).
  - **Lightweight**: `LFM2.5-230M-Q4_K_M` (fast iteration, ultra-low resource consumption).
- **Accurate & Grounded**: Answers are strictly backed by deterministic tool execution against indexed local data, eliminating hallucinations.
- **Zero-friction install**: Designed to bundle cleanly without requiring manual `.env` file editing, Docker containers, or Python environment setup for end users.

## 2. Non-goals (for now)

- Sending, deleting, or modifying emails (read-only scopes strictly enforced).
- Multi-user or hosted cloud deployment.
- Support for email providers other than Gmail (may extend to Outlook/IMAP later).

---

## 3. Tech Stack

| Layer | Choice | Details & Rationale |
|---|---|---|
| **LLM Models** | **Liquid AI LFM2.5** (GGUF Q4_K_M) | `2.6B` (balanced, agentic-tuned) or `230M` (lightweight, rapid iteration) |
| **LLM Runtime** | **llama.cpp** (`llama-server.exe`, b11050) | Auto-downloads prebuilt Windows binary; supports CUDA 13.4 with full layer offload (`-ngl -1`) or CPU (`-ngl 0`) |
| **Configuration** | **Pydantic Settings** (`pydantic-settings`) | Type-safe settings with environment variable overrides and sensible defaults in `settings.py` |
| **Local Store** | **SQLite** (`database.py`) | Indexes `emails` metadata and caches full thread bodies in `emails_content` |
| **Sync & Auth** | **Google OAuth2 (Desktop App Flow)** | Secure PKCE/refresh token auth; full initial backfill + incremental sync using Gmail `historyId` |
| **Agent Orchestration** | **LangGraph / Python** (Planned) | Query classifier → router → tool execution → aggregator → responder graph |
| **API Layer** | **FastAPI** (Planned) | Serves the agent locally and hosts frontend static assets |
| **UI** | **React / Vite** (Planned) | Clean desktop-style chat interface |
| **Packaging** | **PyInstaller / Nuitka** (Planned) | Bundles backend, static frontend, and `llama.cpp` runtime into a native installer |

---

## 4. Architecture

```
                    ┌─────────────────────────────────────────────┐
 User query ──────► │  Query Classifier  (Pure Python / Regex)    │
                    │  Assigns a query_type:                      │
                    │    count_list / content_summary /           │
                    │    date_range / thread_lookup               │
                    │                                             │
                    │  Looks up query_type → allowed tool subset  │
                    │  e.g. content_summary → [search_emails,     │
                    │                          get_email_thread]  │
                    └───────────────────┬─────────────────────────┘
                                        │  (query_type + tool subset)
                                        ▼
                    ┌───────────────────────┐
                    │   Router Node (LLM)   │  Given ONLY the allowed tool subset,
                    │                       │  decides which to call & with what args.
                    └───────────┬───────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │  Tool-Call Node(s)    │  Deterministic local search
                    │  (SQLite + Gmail API) │  (search_emails, get_email_thread)
                    └───────────┬───────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │  Aggregation Node     │  Merge, deduplicate, truncate
                    │  (Deterministic code) │
                    └───────────┬───────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │  Response Node (LLM)  │  Generates final synthesis
                    └───────────┬───────────┘
                                │
                                ▼
                           Final Answer
```

Only the **Router** and **Response** nodes communicate with the local LLM server. Query classification, database filtering, tool dispatch, and deduplication run as pure Python logic to maintain low latency and prevent hallucinations.

### Why the Classifier Exists: Tool Namespace Gating

The classifier is **not** intended to make routing decisions that the LLM could theoretically make itself. Its purpose is to act as a **tool namespace gatekeeper** before the Router ever sees the query.

Instead of giving the Router the full list of all available tools and asking it to pick, the classifier:
1. Assigns a `query_type` using fast, deterministic regex/keyword matching.
2. Looks up a hardcoded `query_type → allowed_tools` mapping.
3. Passes only that **subset** of tools to the Router's prompt.

```python
# agent/classifier.py

QUERY_TYPE_TOOLS: dict[str, list[str]] = {
    "count_list":      ["search_emails"],
    "date_range":      ["search_emails"],
    "content_summary": ["search_emails", "get_email_thread"],
    "thread_lookup":   ["get_email_thread"],
}
```

This matters for two reasons:

- **Small-model reliability**: A 2.6B LLM given 2 constrained tool choices and a narrow, type-specific prompt is significantly more consistent than one given an open-ended "pick any tools" decision. Constraining tool choice to 1–2 options per query type eliminates whole classes of routing mistakes.
- **Scalability**: As InboxIQ grows and new tools are added (e.g. `get_attachment_list`, `search_contacts`, `get_calendar_events`), the Router prompt never balloons in size. Each query type only ever exposes the 1–3 tools actually relevant to it — the classifier absorbs all the complexity of the growing tool registry.

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
   - Message bodies are **not** downloaded in bulk during sync (saving gigabytes of bandwidth and disk).
   - When a thread is queried via `get_email_thread()`, bodies are fetched from Gmail and cached locally in `emails_content` for immediate reuse.

---

## 6. Current Repository Structure

```
InboxIQ/
├── backend/
│   ├── src/
│   │   ├── agent/
│   │   │   ├── __init__.py
│   │   │   ├── llm.py                 # [IMPLEMENTED] Local llama-cpp HTTP client, process hooks, latency logger
│   │   │   ├── tools.py               # [IMPLEMENTED] search_emails & get_email_thread tool interfaces
│   │   │   ├── classifier.py          # [PLANNED] Rule-based / LLM query classifier
│   │   │   ├── router.py              # [PLANNED] Router node emitting tool calls
│   │   │   ├── aggregator.py          # [PLANNED] Tool output formatting and deduplication
│   │   │   ├── responder.py           # [PLANNED] Final synthesis node
│   │   │   └── graph.py               # [PLANNED] LangGraph state graph definition
│   │   ├── bootstrap/
│   │   │   ├── __init__.py
│   │   │   ├── setup_models.py        # [IMPLEMENTED] Auto-downloader for HuggingFace GGUF models
│   │   │   └── setup_llm_server.py    # [IMPLEMENTED] GPU detector (ctypes/smi), llama.cpp downloader & runner
│   │   ├── storage/
│   │   │   ├── __init__.py
│   │   │   └── database.py            # [IMPLEMENTED] SQLite schema, indexes, transaction decorator, search queries
│   │   ├── sync/
│   │   │   ├── __init__.py
│   │   │   └── gmail_sync.py          # [IMPLEMENTED] OAuth2 flow, full sync, history sync, body caching
│   │   ├── utils/
│   │   │   ├── __init__.py
│   │   │   ├── datetime_functions.py  # [IMPLEMENTED] RFC 2822 / ISO date parser with IST/UTC handling
│   │   │   ├── file_utils.py          # [IMPLEMENTED] Streaming file downloader with tqdm progress
│   │   │   └── logging_setup.py       # [IMPLEMENTED] App-wide logging setup
│   │   ├── api/
│   │   │   ├── .gitkeep
│   │   │   ├── server.py              # [PLANNED] FastAPI backend application
│   │   │   └── mcp_server.py          # [PLANNED] Model Context Protocol server adapter
│   │   ├── setup_wizard/
│   │   │   └── static/.gitkeep        # [PLANNED] First-run local onboarding web interface
│   │   ├── eval/
│   │   │   └── .gitkeep               # [PLANNED] Evaluation benchmark queries & test harness
│   │   ├── settings.py                # [IMPLEMENTED] Central Pydantic BaseSettings
│   │   └── main.py                    # [IN PROGRESS] Top-level application entry point
│   ├── scripts/
│   │   └── sqlite_summary.py          # [IMPLEMENTED] Developer utility to inspect DB table counts & schema
│   ├── tests/
│   │   ├── agent/test_tools.py        # [STUB] Tool tests
│   │   ├── storage/test_sqlite_db.py  # [STUB] Database query tests
│   │   └── sync/test_gmail_sync.py    # [STUB] Gmail sync & parser tests
│   ├── data/                          # [GENERATED] SQLite database files (inboxiq.db)
│   ├── models/                        # [GENERATED] Hugging Face GGUF model files
│   ├── llama-cpp/                     # [GENERATED] Extracted llama.cpp server binaries & DLLs
│   └── logs/                          # [GENERATED] Application runtime logs
├── frontend/                          # [PLANNED] React frontend application
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
    limit: int = 50,                # Max results returned (ordered newest-first)
) -> list[dict]:
    """Queries indexed email metadata from SQLite; does not load full body text."""

def get_email_thread(
    thread_id: str                  # Gmail thread identifier
) -> dict:
    """Returns thread metadata and all messages with full body text (cached locally)."""
```

---

## 8. Development & Implementation Roadmap

### Phase 1: Core Foundation (COMPLETED)
- [x] **Settings & Configuration**: Centralized settings via `settings.py` for URLs, ports, context sizes, and batch parameters.
- [x] **Data Access Layer**: SQLite database schema (`emails`, `emails_content`, `sync_state`) with indexed search fields and transaction decorators.
- [x] **Gmail Sync Engine**: OAuth2 desktop authentication, bulk message ingestion, incremental history sync via `historyId`, and on-demand body caching.
- [x] **Model Bootstrap**: Automatic download and verification of GGUF models (`LFM2.5-2.6B` and `LFM2.5-230M`).
- [x] **Runtime & Hardware Auto-Detection**: Detection of NVIDIA GPUs via direct `ctypes` CUDA driver hooks (`cuInit`/`cuDeviceGetCount`) and `nvidia-smi` fallback; automated download of CUDA 13.4 or CPU `llama.cpp` releases with dynamic `-ngl -1` / `0` parameterization.
- [x] **LLM Client & Process Management**: Background `llama-server.exe` launch, health check polling, OpenAI-compatible `/v1/chat/completions` client, and latency tracking.
- [x] **Tool Definitions**: Implemented `search_emails` and `get_email_thread` linked directly to database and sync caching.

### Phase 2: Agent Graph & Orchestration (NEXT UP)
- [ ] **Query Classifier (`agent/classifier.py`)**: Fast regex/keyword classifier that assigns a `query_type` and looks up the corresponding `QUERY_TYPE_TOOLS` mapping. Passes only the allowed tool subset to the Router — keeps the Router prompt small and reliable regardless of how many tools are added to the project over time.
- [ ] **Router Node (`agent/router.py`)**: Receives the `query_type` and its pre-filtered tool subset from the classifier. Uses the LLM to decide argument values (dates, keywords, sender filters etc.) and ordering of tool calls — not which tools to use.
- [ ] **Aggregator Node (`agent/aggregator.py`)**: Deduplication and formatting of SQLite results before response generation.
- [ ] **Response Node (`agent/responder.py`)**: Grounded answer generation using tool context.
- [ ] **LangGraph Integration (`agent/graph.py`)**: End-to-end graph state machine coordinating nodes and tool dispatches.

### Phase 3: Testing & Evaluation
- [ ] Implement unit tests for `storage/database.py`, `sync/gmail_sync.py`, and `agent/tools.py`.
- [ ] Create `eval/eval_queries.json` with a representative suite of test queries against real inbox structures.
- [ ] Validate accuracy and benchmark latency between balanced (`2.6B`) and lightweight (`230M`) models on GPU vs CPU.

### Phase 4: Local Server & API
- [ ] Build FastAPI server (`api/server.py`) exposing `/query`, `/sync`, and health endpoints.
- [ ] Optional: Add Model Context Protocol (`api/mcp_server.py`) interface to expose InboxIQ tools to external LLM clients.

### Phase 5: Frontend & User Onboarding
- [ ] Build React UI (desktop-tailored chat interface with citation chips and thread preview).
- [ ] Implement first-run setup wizard (`setup_wizard/`) for browser-based OAuth consent and model initialization.

### Phase 6: Packaging & Distribution
- [ ] Package backend and static frontend with PyInstaller or Nuitka.
- [ ] Bundle prebuilt `llama-server` runtime and setup scripts into a standalone executable.

---

## 9. Future Extensions

- Multi-account Gmail switching.
- Attachments metadata indexing and local search.
- Support for other email providers (Outlook / IMAP).
- Background recurring email digests (e.g. daily executive brief).