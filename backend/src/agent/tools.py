"""
Here we store all the tools which we expose to our LLM agent.
"""


def search_emails(
    keyword: str | None = None,
    sender: str | None = None,
    recipient: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    label: str | None = None,
    limit: int = 50,
) -> list[dict]:
    pass


def get_email_thread(thread_id: str) -> dict:
    pass