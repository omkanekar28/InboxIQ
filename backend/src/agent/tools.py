"""
Here we store all the tools which we expose to our LLM agent.
"""
from storage.database import Database
from sync.gmail_sync import GmailSync


_db: Database | None = None
_gmail_sync: GmailSync | None = None


def init_tools(db: Database, gmail_sync: GmailSync) -> None:
    """Bind the tools module to a Database and GmailSync instance before use."""
    global _db, _gmail_sync
    _db = db
    _gmail_sync = gmail_sync


def search_emails(
    keyword: str | None = None,
    sender: str | None = None,
    recipient: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    label: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Search emails using any combination of filters.

    All provided arguments are applied as AND conditions in a single SQL
    query — each extra argument narrows the result set rather than
    producing an overlapping separate one.

    Args:
        keyword:    Match against subject or snippet (case-insensitive).
        sender:     Partial match against the sender field.
        recipient:  Partial match against the recipient field.
        date_from:  Inclusive lower bound (any common date format).
        date_to:    Inclusive upper bound (any common date format).
        label:      Gmail label to filter by (e.g. "INBOX", "UNREAD").
        limit:      Maximum number of results to return (default 50).

    Returns:
        List of email dicts ordered newest-first.
    """
    assert _db is not None, "Tools not initialised — call init_tools(db, gmail_sync) first."
    return _db.search_emails(
        keyword=keyword,
        sender=sender,
        recipient=recipient,
        date_from=date_from,
        date_to=date_to,
        label=label,
        limit=limit,
    )


def get_email_thread(thread_id: str) -> dict:
    """Fetch all emails in a thread by thread_id, including full body text.

    For each email in the thread:
      1. Checks the local DB cache for the body.
      2. On a cache miss, fetches the full body from Gmail and caches it.
    Then returns the complete thread with all bodies populated.

    Args:
        thread_id: The Gmail thread ID to retrieve.

    Returns:
        Dict with 'thread_id' and 'emails' (list of email dicts, oldest-first).
    """
    assert _db is not None and _gmail_sync is not None, \
        "Tools not initialised — call init_tools(db, gmail_sync) first."

    # First get all email IDs in the thread (metadata only, fast)
    thread = _db.get_email_thread(thread_id)

    for email in thread["emails"]:
        if email.get("body") is None:
            # Cache miss — fetch from Gmail and cache for future calls
            email["body"] = _gmail_sync.fetch_and_cache_body(email["id"])

    return thread


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_emails",
            "description": (
                "Search for emails using various filters. "
                "Does not fetch full email bodies."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "Keywords or search term to match against subject, snippet, or sender (e.g. 'interview', 'SQLite', 'GitHub').",
                    },
                    "sender": {
                        "type": "string",
                        "description": "Filter by sender name or email address (e.g. 'Indeed', 'Alice', 'Uber'). Use this whenever the user asks for emails from someone.",
                    },
                    "recipient": {
                        "type": "string",
                        "description": "Filter by recipient email address. Only use when the user explicitly asks for emails sent TO a specific recipient.",
                    },
                    "date_from": {
                        "type": "string",
                        "description": "Inclusive lower bound (any common date format).",
                    },
                    "date_to": {
                        "type": "string",
                        "description": "Inclusive upper bound (any common date format).",
                    },
                    "label": {
                        "type": "string",
                        "description": "Gmail label to filter by (e.g. \"INBOX\", \"UNREAD\").",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default 50).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_email_thread",
            "description": "Fetch all emails in a thread by thread_id, including full body text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "thread_id": {
                        "type": "string",
                        "description": "The Gmail thread ID to retrieve.",
                    },
                },
                "required": ["thread_id"],
            },
        },
    },
]

TOOL_FUNCTIONS = {
    "search_emails": search_emails,
    "get_email_thread": get_email_thread
}


# FOR DEBUGGING
# if __name__ == "__main__":
#     import json
#     from settings import settings
#     from storage.database import Database
#     from sync.gmail_sync import GmailSync

#     db = Database(
#         store_dir=settings.DB_STORE_DIR,
#         sqlite_filename=settings.DB_SQLITE_FILENAME,
#         search_email_fields=settings.SEARCH_EMAIL_FIELDS,
#         email_thread_fields=settings.EMAIL_THREAD_FIELDS,
#     )
#     gmail_sync = GmailSync(db)
#     init_tools(db, gmail_sync)

#     # Test search_emails
#     # results = search_emails(keyword="AI", date_from="2026-09-11", limit=5)
#     # print(json.dumps(results, indent=4))

#     # Test get_email_thread — paste a real thread_id from the results above 
#     # print(json.dumps(get_email_thread("1a092a2f58fae2ff"), indent=4))