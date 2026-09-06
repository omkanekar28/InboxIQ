# InboxIQ (Local Email Agent)

A fully local, CPU-only agentic assistant that answers natural-language questions about your Gmail history — e.g. *"Summarize all mails I sent to xyz in the past 3 months"* or *"List all interviews I was invited to this year"* — without sending any data to the cloud.

Everything in this stack is free, open source, and runs offline after first setup.

---

## 1. Goals

- **Local-first**: no data leaves the machine; no paid APIs.
- **Low latency, CPU-only**: usable on a laptop without a GPU.
- **Accurate**: tool-call-grounded answers, not hallucinated summaries.
- **Zero-friction install**: a non-technical user should be able to run one setup step and start using it — no `.env` editing, no Docker, no manual Python environment setup.

## 2. Non-goals (for now)

- Sending/deleting/modifying emails (read-only scopes only).
- Multi-user / hosted deployment.
- Support for providers other than Gmail (may extend later).

---

## 3. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| LLM (planner + responder) | **LFM2.5-2.6B**, GGUF quantized (Q4_K_M or QAD-Q4_0) | Agentic-tuned, 128K context, native tool calling, fast on CPU |
| LLM runtime | **llama.cpp** (server mode) | CPU-optimized, no GPU needed, bundleable as a static binary |
| Metadata store | **SQLite** | Stores email metadata (sender, recipient, date, label, thread_id, subject, snippet); queried directly for search |
| Orchestration | **LangGraph** | Router → tool-call → aggregation → response graph |
| API layer | **FastAPI** | Serves the agent locally; also the base for an MCP server wrapper |
| Auth | **Google OAuth2 (installed-app / PKCE flow)** | No client secret needed to keep private; standard for CLI/local tools |
| Packaging | **PyInstaller/Nuitka** + bundled `llama.cpp` binary | Single executable per OS, no Python/Docker required by end user |

> Note: All search — keyword/metadata filtering (date range, sender, label, subject/snippet text) — happens directly in SQLite via the two tools (`search_emails`, `get_email_thread`).

---

## 4. Architecture

```
                    ┌───────────────────────┐
 User query ──────► │  Query Classifier     │  (rule-based first; LLM fallback)
                    │  date_range /         │
                    │  content_summary /    │
                    │  count_list /         │
                    │  thread_lookup        │
                    └───────────┬───────────┘
                              ▼
                    ┌───────────────────────┐
                    │   Router Node (LLM)   │  decides tool(s) + args
                    └──────────┬────────────┘
                              ▼
                    ┌───────────────────────┐
                    │  Tool-Call Node(s)    │  deterministic code
                    │  (SQLite + Gmail API) │
                    └─────────┬─────────────┘
                              ▼
                    ┌───────────────────────┐
                    │  Aggregation Node     │  merge/dedupe/truncate
                    │  (deterministic code) │
                    └─────────┬─────────────┘
                              ▼
                    ┌───────────────────────┐
                    │  Response Node (LLM)  │  writes final answer
                    └─────────┬─────────────┘
                              ▼
                         Final Answer
```

Only the **Router** and **Response** nodes call the LLM. Classification, tool execution, and aggregation are plain Python — this keeps latency down and reduces hallucination surface.

---

## 5. Data Sync (Gmail → local store)

- **First boot**: full backfill — paginate all messages via Gmail API, extract metadata (sender, recipient, date, label, subject, snippet) into SQLite.
- **Every subsequent boot**: incremental sync using Gmail's `users.history.list` with the last stored `historyId` (captures new mail, label changes, deletions — not just new sends).
- **Fallback**: if `historyId` has expired (Gmail expires history after ~7 days of inactivity), fall back to a date-range re-sync from the last known message date, de-duped by `message_id`.
- Store `last_history_id` and `last_sync_at` in a `sync_state` table.

---

## 6. Repo Structure (proposed)

```
InboxIQ/
├── backend/
│   ├── agent/
│   │   ├── classifier.py        # rule-based + optional LLM query classification
│   │   ├── router.py             # LLM router node
│   │   ├── tools.py               # tool implementations (search_emails, etc.)
│   │   ├── aggregator.py          # merge/dedupe tool outputs
│   │   ├── responder.py           # LLM response node
│   │   └── graph.py                # LangGraph wiring of the above
│   ├── sync/
│   │   └── gmail_sync.py          # first-boot backfill + incremental history sync
│   ├── storage/
│   │   └── db.py                   # SQLite schema + queries
│   ├── llm/
│   │   └── llamacpp_client.py      # wrapper around local llama.cpp server calls
│   ├── api/
│   │   ├── server.py                # FastAPI app, /query endpoint, serves ../../frontend/dist as static files
│   │   └── mcp_server.py             # MCP wrapper exposing the same tools
│   ├── setup_wizard/
│   │   ├── wizard_server.py          # local web page for first-run OAuth + config
│   │   └── static/                    # minimal HTML/JS for the wizard page
│   ├── eval/
│   │   └── eval_queries.json         # hand-written test queries + expected answers
│   └── requirements.txt
├── frontend/                        # React app (built in Lovable), exported + checked in here
│   ├── src/
│   ├── package.json
│   └── dist/                          # production build output, served by FastAPI — gitignored
├── packaging/
│   ├── build.spec                    # PyInstaller spec (bundles backend)
│   └── bundle_llamacpp.sh            # script to fetch/compile llama.cpp binary for bundling
├── models/                            # gitignored — GGUF model downloaded on first run
└── README.md
```

---

## 7. Tool Schemas

The agent has exactly two tools:

```python
def search_emails(
    query: str | None = None,       # keyword match against subject/snippet (SQLite LIKE/FTS5)
    sender: str | None = None,       # filter: email FROM this address/name
    recipient: str | None = None,    # filter: email SENT TO this address
    date_from: str | None = None,    # ISO date, inclusive lower bound
    date_to: str | None = None,      # ISO date, inclusive upper bound
    label: str | None = None,        # Gmail label (system or custom); excludes SPAM/TRASH by default
    limit: int = 50,
) -> list[dict]:  # light metadata only: sender, recipient, subject, snippet, date, thread_id
                  # — no full body

def get_email_thread(thread_id: str) -> dict:  # full thread/body content, called selectively
                                                 # on whichever results from search_emails
                                                 # the agent decides are relevant
```

`search_emails` is a single SQLite query against indexed columns (sender, recipient, date, label) plus keyword matching on subject/snippet — no vector index involved. `get_email_thread` is only called on the subset of results the Router decides actually need full content, keeping context small and cheap.

Keep schemas flat and minimal — a 2.6B model's tool-call reliability degrades faster than a larger model's on deeply nested/optional-heavy schemas.

---

## 8. Query Classification (Phase detail)

Rule-based first pass (regex/keyword), LLM fallback only for ambiguous cases:

| Pattern | Type | Router behavior |
|---|---|---|
| "how many", "count" | `count_list` | Single tool call, format count in code, may skip LLM response pass entirely |
| "list", "which" | `count_list` | Tool call + bullet-list formatting |
| "summarize", "summary" | `content_summary` | Tool call(s) + `get_email_thread` on top results + prose response |
| explicit date phrases without summary intent | `date_range` | Narrow tool call, minimal response formatting |

This constrains the Router LLM's prompt per query type instead of using one large prompt to handle every case at once — smaller, more specific prompts are more reliable at this model size.

---

## 9. Build Phases

1. **Data access layer** — Gmail OAuth, SQLite schema, sync logic (Section 5)
2. **Tool layer** — implement and unit-test `tools.py` against real data, independent of the LLM
3. **Agent orchestration** — LangGraph graph wiring, query classifier, prompt design for Router/Response nodes
4. **CPU serving** — llama.cpp server integration, GGUF variant benchmarking (QAD-Q4_0 vs Q4_K_M)
5. **Accuracy hardening** — date parsing, sender/recipient disambiguation, dedup logic, `eval_queries.json` regression suite
6. **Packaging & distribution** (see below)

---

## 10. Packaging & Distribution Plan (Phase 6)

Goal: a user downloads one file per OS and runs it — no Python, no Docker, no manual config editing.

1. **Bundle the app**: PyInstaller (or Nuitka for better performance) compiles the FastAPI app + agent code into a single native executable per platform.
2. **Bundle the LLM runtime**: compile/include a static `llama.cpp` server binary inside the package.
3. **Model download on first run**: on first launch, auto-download the GGUF model file from Hugging Face into `~/.local-email-agent/models/` with a progress indicator — same pattern as `ollama run` pulling a model on first use.
4. **Setup wizard instead of `.env`**: first launch opens a local web page (`localhost:PORT`, auto-opened in the default browser) served by `wizard_server.py`. It walks the user through:
   - "Connect Gmail" → standard Google OAuth consent screen (PKCE flow, no exposed client secret)
   - Writes the resulting token + any preferences to `~/.local-email-agent/config.json` automatically
5. **OAuth client**: register one Google Cloud OAuth client for the project and embed the public client ID in the binary (installed-app flow doesn't require the secret to stay private) — the same approach tools like `gh` and `rclone` use, so users never create their own Google Cloud project.
6. **Distribution**: package as `Setup.exe` (Windows), `.dmg` (macOS), `.AppImage` (Linux). Double-click → wizard runs once → tray icon / local web UI for ongoing use.

Sequencing note: build and validate the agent with a normal Python + local llama.cpp server setup first (Phases 1–5), then invest in the installer experience once core logic and accuracy are solid — packaging a half-finished agent wastes the effort.

---

## 11. Testing & Evaluation

### 11.1 Automated Tests

Use **pytest** as the primary automated testing framework. Tests should be developed alongside each feature rather than added only at the end.

Repo structure:

```text
tests/
├── agent/
│   ├── test_classifier.py
│   ├── test_tools.py
│   └── test_aggregator.py
├── sync/
│   └── test_gmail_sync.py
├── storage/
│   ├── test_db.py
│   └── test_vector_store.py
└── integration/
    └── test_agent_flow.py
```

Testing principles:

- Every new behavior should have corresponding pytest coverage.
- Every bug discovered should result in a regression test before/alongside the fix.
- Prioritize deterministic components: SQLite queries, Gmail tools, classification, filtering, deduplication, aggregation, and sync logic.
- Mock external Gmail API calls in unit tests; do not require a real Google account for the normal test suite.
- Keep LLM-dependent tests limited to integration/behavioral tests; avoid asserting exact wording of LLM responses.
- Run the full pytest suite before merging changes.
- Maintain a simple test matrix/checklist as features are added so important edge cases are not forgotten.

### 11.2 Evaluation

Maintain `eval/eval_queries.json` — a hand-written set of ~20–30 queries against your own real inbox with known correct answers (message counts, specific senders, date ranges). Re-run after any change to prompts, tool schemas, or the classifier. This is the primary signal for whether accuracy is improving, since model benchmarks won't reflect your actual inbox structure.

Pytest verifies that individual components and system behaviors work correctly; `eval_queries.json` verifies that the complete agent produces correct answers for realistic inbox questions.

---

## 12. Open Items / Future Extensions

- Multi-account support
- Attachments search
- Outlook/other providers
- Background "always-on" digest mode (e.g. daily summary) — noted as a good fit for this model class per Liquid AI's own positioning, but out of scope for v1