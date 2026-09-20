"""
Synthetic dataset of 30 realistic emails for InboxIQ testing and evaluation.

Anchored relative to reference date: 2026-09-20.
Includes realistic senders, subjects, snippets, categories, labels,
timestamps, and threaded conversations with full bodies.
"""

import json
from datetime import datetime, timezone
from storage.database import Database


def _to_ms(dt_str: str) -> int:
    """Helper to convert YYYY-MM-DD HH:MM:SS to epoch milliseconds."""
    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


# -------------------------------------------------------------------
# 30 Synthetic Email Metadata Records
# -------------------------------------------------------------------
MOCK_EMAILS = [
    # Work Project Discussion Thread (3 messages in th_proj_alice)
    {
        "id": "em_01",
        "thread_id": "th_proj_alice",
        "sender": "Alice Smith <alice.smith@techcorp.com>",
        "recipient": "alex.morgan@example.com",
        "subject": "Q3 Architecture & Database Selection",
        "snippet": "Hey Alex, wanted to kick off the discussion regarding our local storage choice...",
        "labels": ["INBOX", "WORK"],
        "date": "Mon, 14 Sep 2026 10:00:00 +0000",
        "internal_date_ms": _to_ms("2026-09-14 10:00:00"),
    },
    {
        "id": "em_02",
        "thread_id": "th_proj_alice",
        "sender": "Alex Morgan <alex.morgan@example.com>",
        "recipient": "alice.smith@techcorp.com",
        "subject": "Re: Q3 Architecture & Database Selection",
        "snippet": "Hi Alice, SQLite seems much lighter and has zero overhead for local desktop apps...",
        "labels": ["SENT", "WORK"],
        "date": "Mon, 14 Sep 2026 14:30:00 +0000",
        "internal_date_ms": _to_ms("2026-09-14 14:30:00"),
    },
    {
        "id": "em_03",
        "thread_id": "th_proj_alice",
        "sender": "Alice Smith <alice.smith@techcorp.com>",
        "recipient": "alex.morgan@example.com",
        "subject": "Re: Q3 Architecture & Database Selection",
        "snippet": "Agreed! Final decision: we will proceed with SQLite and set the schema migration deadline to Oct 1st...",
        "labels": ["INBOX", "WORK", "IMPORTANT"],
        "date": "Tue, 15 Sep 2026 09:15:00 +0000",
        "internal_date_ms": _to_ms("2026-09-15 09:15:00"),
    },

    # Work Sprint Thread (2 messages in th_sprint_bob)
    {
        "id": "em_04",
        "thread_id": "th_sprint_bob",
        "sender": "Bob Chen <bob.chen@techcorp.com>",
        "recipient": "alex.morgan@example.com",
        "subject": "Sprint Planning Rescheduled to Monday",
        "snippet": "Hi team, due to client demos, sprint planning is moved to Monday at 10 AM PST...",
        "labels": ["INBOX", "WORK"],
        "date": "Fri, 18 Sep 2026 11:00:00 +0000",
        "internal_date_ms": _to_ms("2026-09-18 11:00:00"),
    },
    {
        "id": "em_05",
        "thread_id": "th_sprint_bob",
        "sender": "Bob Chen <bob.chen@techcorp.com>",
        "recipient": "alex.morgan@example.com",
        "subject": "Re: Sprint Planning Rescheduled to Monday",
        "snippet": "Quick reminder: Please bring your velocity estimates to the room...",
        "labels": ["INBOX", "WORK"],
        "date": "Fri, 18 Sep 2026 15:45:00 +0000",
        "internal_date_ms": _to_ms("2026-09-18 15:45:00"),
    },

    # Job Hunting / Indeed (3 emails: 2 in past 2 months, 1 older than 5 months)
    {
        "id": "em_06",
        "thread_id": "th_ind_01",
        "sender": "Indeed Apply <indeedapply@indeed.com>",
        "recipient": "alex.morgan@example.com",
        "subject": "Indeed Application: Senior AI Engineer at InnovateTech",
        "snippet": "Your application for Senior AI Engineer was submitted to InnovateTech...",
        "labels": ["INBOX", "CATEGORY_UPDATES"],
        "date": "Sat, 19 Sep 2026 08:30:00 +0000",
        "internal_date_ms": _to_ms("2026-09-19 08:30:00"),
    },
    {
        "id": "em_07",
        "thread_id": "th_ind_02",
        "sender": "Indeed Job Alert <donotreply@jobalert.indeed.com>",
        "recipient": "alex.morgan@example.com",
        "subject": "15 new Python & Agentic AI jobs in Remote",
        "snippet": "Top recommendations: AI Agent Developer at Horizon Labs, LLM Systems Engineer...",
        "labels": ["INBOX", "CATEGORY_UPDATES"],
        "date": "Mon, 10 Aug 2026 12:00:00 +0000",
        "internal_date_ms": _to_ms("2026-08-10 12:00:00"),
    },
    {
        "id": "em_08",
        "thread_id": "th_ind_03",
        "sender": "Indeed Job Alert <donotreply@jobalert.indeed.com>",
        "recipient": "alex.morgan@example.com",
        "subject": "Indeed: Spring Hiring Surge - Software Engineer Jobs",
        "snippet": "Companies are hiring software engineers across Bangalore and Remote...",
        "labels": ["CATEGORY_UPDATES"],
        "date": "Wed, 01 Apr 2026 10:00:00 +0000",
        "internal_date_ms": _to_ms("2026-04-01 10:00:00"),
    },

    # Interviews & Recruiters
    {
        "id": "em_09",
        "thread_id": "th_recruiter_01",
        "sender": "Sarah Jenkins <sarah.jenkins@robertwalters.com>",
        "recipient": "alex.morgan@example.com",
        "subject": "Interview Invitation: Lead AI Systems Engineer at FinTech Global",
        "snippet": "Hi Alex, I came across your profile and would love to invite you for an interview with FinTech Global...",
        "labels": ["INBOX", "UNREAD", "IMPORTANT"],
        "date": "Thu, 17 Sep 2026 14:00:00 +0000",
        "internal_date_ms": _to_ms("2026-09-17 14:00:00"),
    },
    {
        "id": "em_10",
        "thread_id": "th_recruiter_02",
        "sender": "Greenhouse Recruiting <no-reply@greenhouse.io>",
        "recipient": "alex.morgan@example.com",
        "subject": "Interview Invitation: Technical Screen with Anthropic Partner",
        "snippet": "Thank you for applying. We would like to schedule a 45-minute technical screen...",
        "labels": ["INBOX", "UNREAD"],
        "date": "Sat, 19 Sep 2026 16:20:00 +0000",
        "internal_date_ms": _to_ms("2026-09-19 16:20:00"),
    },
    {
        "id": "em_11",
        "thread_id": "th_linkedin_01",
        "sender": "LinkedIn Jobs <jobs-listings@linkedin.com>",
        "recipient": "alex.morgan@example.com",
        "subject": "Alex, 8 jobs match your alert 'AI Engineer'",
        "snippet": "New jobs from Meta, Stripe, and Databricks match your criteria...",
        "labels": ["INBOX", "CATEGORY_UPDATES"],
        "date": "Wed, 16 Sep 2026 07:00:00 +0000",
        "internal_date_ms": _to_ms("2026-09-16 07:00:00"),
    },
    {
        "id": "em_12",
        "thread_id": "th_recruiter_03",
        "sender": "Talent Team <careers@scaleops.ai>",
        "recipient": "alex.morgan@example.com",
        "subject": "Update on your application with ScaleOps",
        "snippet": "Thank you for taking the time to speak with us. Unfortunately, we have decided to move forward with another candidate...",
        "labels": ["INBOX"],
        "date": "Sat, 01 Aug 2026 11:30:00 +0000",
        "internal_date_ms": _to_ms("2026-08-01 11:30:00"),
    },

    # Developer & Infrastructure Notifications
    {
        "id": "em_13",
        "thread_id": "th_gh_01",
        "sender": "GitHub <notifications@github.com>",
        "recipient": "alex.morgan@example.com",
        "subject": "[GitHub] PR #42 merged: 'feat: add streaming support to llama client'",
        "snippet": "alex-dev merged commit 8f19ac into main. 4 checks passed...",
        "labels": ["INBOX", "UNREAD", "CATEGORY_UPDATES"],
        "date": "Tue, 15 Sep 2026 08:00:00 +0000",
        "internal_date_ms": _to_ms("2026-09-15 08:00:00"),
    },
    {
        "id": "em_14",
        "thread_id": "th_gh_02",
        "sender": "GitHub <notifications@github.com>",
        "recipient": "alex.morgan@example.com",
        "subject": "[GitHub] Issue #50 opened by alex-dev: 'Memory leak during long context eval'",
        "snippet": "When running 128k context windows, memory does not free up properly...",
        "labels": ["INBOX", "UNREAD", "CATEGORY_UPDATES"],
        "date": "Thu, 17 Sep 2026 19:10:00 +0000",
        "internal_date_ms": _to_ms("2026-09-17 19:10:00"),
    },
    {
        "id": "em_15",
        "thread_id": "th_gh_03",
        "sender": "GitHub <notifications@github.com>",
        "recipient": "alex.morgan@example.com",
        "subject": "[GitHub] Security Alert: Dependabot detected 1 moderate vulnerability in pyproject.toml",
        "snippet": "Bump requests from 2.31.0 to 2.32.0 in backend...",
        "labels": ["INBOX", "CATEGORY_UPDATES"],
        "date": "Sat, 19 Sep 2026 21:00:00 +0000",
        "internal_date_ms": _to_ms("2026-09-19 21:00:00"),
    },
    {
        "id": "em_16",
        "thread_id": "th_gcp_01",
        "sender": "Google Cloud <CloudPlatform-noreply@google.com>",
        "recipient": "alex.morgan@example.com",
        "subject": "Google Cloud: Monthly Invoice September 2026 available",
        "snippet": "Your monthly invoice for account 4349-9336-1947 is now ready. Total: $12.45...",
        "labels": ["INBOX", "CATEGORY_UPDATES"],
        "date": "Wed, 02 Sep 2026 09:00:00 +0000",
        "internal_date_ms": _to_ms("2026-09-02 09:00:00"),
    },
    {
        "id": "em_17",
        "thread_id": "th_vercel_01",
        "sender": "Vercel <notifications@vercel.com>",
        "recipient": "alex.morgan@example.com",
        "subject": "Production deployment succeeded: inboxiq-web",
        "snippet": "Deployment inboxiq-web-d79a2 completed in 42s. URL: https://inboxiq.app...",
        "labels": ["INBOX", "CATEGORY_UPDATES"],
        "date": "Fri, 18 Sep 2026 13:00:00 +0000",
        "internal_date_ms": _to_ms("2026-09-18 13:00:00"),
    },
    {
        "id": "em_18",
        "thread_id": "th_aws_01",
        "sender": "AWS Notifications <no-reply-aws@amazon.com>",
        "recipient": "alex.morgan@example.com",
        "subject": "AWS Budget Notification: 85% of monthly budget reached",
        "snippet": "Your forecast usage has exceeded 85% of your $50 monthly threshold...",
        "labels": ["INBOX", "CATEGORY_UPDATES"],
        "date": "Sat, 15 Aug 2026 04:00:00 +0000",
        "internal_date_ms": _to_ms("2026-08-15 04:00:00"),
    },

    # Financial Receipts & Purchases
    {
        "id": "em_19",
        "thread_id": "th_stripe_01",
        "sender": "Stripe <invoices@stripe.com>",
        "recipient": "alex.morgan@example.com",
        "subject": "Your receipt from Anthropic Claude API (#2026-09-01)",
        "snippet": "Receipt #2026-09-01 for $49.00 paid on September 1, 2026...",
        "labels": ["INBOX", "STARRED", "CATEGORY_UPDATES"],
        "date": "Tue, 01 Sep 2026 10:00:00 +0000",
        "internal_date_ms": _to_ms("2026-09-01 10:00:00"),
    },
    {
        "id": "em_20",
        "thread_id": "th_amazon_01",
        "sender": "Amazon.in <auto-confirm@amazon.in>",
        "recipient": "alex.morgan@example.com",
        "subject": "Delivered: Keychron K2 Mechanical Keyboard",
        "snippet": "Your package was delivered to resident. Track package or return items...",
        "labels": ["INBOX", "CATEGORY_UPDATES"],
        "date": "Sat, 12 Sep 2026 16:30:00 +0000",
        "internal_date_ms": _to_ms("2026-09-12 16:30:00"),
    },
    {
        "id": "em_21",
        "thread_id": "th_chase_01",
        "sender": "Chase Bank <no-reply@alertsp.chase.com>",
        "recipient": "alex.morgan@example.com",
        "subject": "Transaction Alert: Large purchase on your Sapphire card",
        "snippet": "A charge of $249.00 at Apple Store was authorized on your card ending in 9801...",
        "labels": ["INBOX", "CATEGORY_UPDATES"],
        "date": "Thu, 10 Sep 2026 18:45:00 +0000",
        "internal_date_ms": _to_ms("2026-09-10 18:45:00"),
    },
    {
        "id": "em_22",
        "thread_id": "th_uber_old",
        "sender": "Uber Receipts <uber.us@uber.com>",
        "recipient": "alex.morgan@example.com",
        "subject": "Your Wednesday evening ride with Uber",
        "snippet": "Total: $18.50. Thanks for riding with Uber! Driver: David...",
        "labels": ["CATEGORY_UPDATES"],
        "date": "Wed, 10 Jun 2026 22:15:00 +0000",  # In June 2026 - NOT this month!
        "internal_date_ms": _to_ms("2026-06-10 22:15:00"),
    },
    {
        "id": "em_23",
        "thread_id": "th_spotify_01",
        "sender": "Spotify <no-reply@spotify.com>",
        "recipient": "alex.morgan@example.com",
        "subject": "Your Spotify Premium Family receipt",
        "snippet": "Thanks for subscribing to Spotify. We received your payment of $16.99...",
        "labels": ["INBOX", "CATEGORY_UPDATES"],
        "date": "Sat, 05 Sep 2026 08:00:00 +0000",
        "internal_date_ms": _to_ms("2026-09-05 08:00:00"),
    },

    # Newsletters & Subscriptions
    {
        "id": "em_24",
        "thread_id": "th_news_01",
        "sender": "TLDR AI <dan@tldrnewsletter.com>",
        "recipient": "alex.morgan@example.com",
        "subject": "TLDR AI: Liquid AI releases LFM2.5 Thinking models",
        "snippet": "Liquid AI introduces hybrid architectures with test-time compute for edge devices...",
        "labels": ["INBOX", "CATEGORY_UPDATES"],
        "date": "Sat, 19 Sep 2026 11:30:00 +0000",
        "internal_date_ms": _to_ms("2026-09-19 11:30:00"),
    },
    {
        "id": "em_25",
        "thread_id": "th_news_02",
        "sender": "The Pragmatic Engineer <newsletter@pragmaticengineer.com>",
        "recipient": "alex.morgan@example.com",
        "subject": "The Pragmatic Engineer: Scaling local LLM architectures",
        "snippet": "Gergely Orosz breaks down local-first AI deployments and memory optimization...",
        "labels": ["INBOX", "CATEGORY_UPDATES"],
        "date": "Fri, 18 Sep 2026 14:00:00 +0000",
        "internal_date_ms": _to_ms("2026-09-18 14:00:00"),
    },
    {
        "id": "em_26",
        "thread_id": "th_news_03",
        "sender": "Crunchyroll <hello@mail.crunchyroll.com>",
        "recipient": "alex.morgan@example.com",
        "subject": "New Fall Anime Lineup Announced!",
        "snippet": "Stream the biggest new releases this season starting October...",
        "labels": ["CATEGORY_PROMOTIONS"],
        "date": "Sun, 13 Sep 2026 03:00:00 +0000",
        "internal_date_ms": _to_ms("2026-09-13 03:00:00"),
    },
    {
        "id": "em_27",
        "thread_id": "th_news_04",
        "sender": "Medium Daily Digest <digest@medium.com>",
        "recipient": "alex.morgan@example.com",
        "subject": "Stories for Alex: 5 advanced SQLite query optimizations",
        "snippet": "Learn how to use composite indexes and covering queries for sub-millisecond lookups...",
        "labels": ["CATEGORY_UPDATES"],
        "date": "Tue, 08 Sep 2026 07:00:00 +0000",
        "internal_date_ms": _to_ms("2026-09-08 07:00:00"),
    },

    # Personal & Meetings
    {
        "id": "em_28",
        "thread_id": "th_colleague_carol",
        "sender": "Carol Danvers <carol@aerotech.org>",
        "recipient": "alex.morgan@example.com",
        "subject": "Lunch next week?",
        "snippet": "Hey Alex, are you free for lunch near the tech park next Tuesday? Let me know...",
        "labels": ["INBOX"],
        "date": "Mon, 07 Sep 2026 15:00:00 +0000",
        "internal_date_ms": _to_ms("2026-09-07 15:00:00"),
    },
    {
        "id": "em_29",
        "thread_id": "th_travel_01",
        "sender": "Airbnb <automated@airbnb.com>",
        "recipient": "alex.morgan@example.com",
        "subject": "Reservation confirmed: Mountain View Chalet in Manali",
        "snippet": "Check-in is Oct 10, 2026. Review directions and host guidelines...",
        "labels": ["INBOX", "CATEGORY_UPDATES"],
        "date": "Tue, 25 Aug 2026 12:00:00 +0000",
        "internal_date_ms": _to_ms("2026-08-25 12:00:00"),
    },
    {
        "id": "em_30",
        "thread_id": "th_zoom_01",
        "sender": "Zoom Video Communications <no-reply@zoom.us>",
        "recipient": "alex.morgan@example.com",
        "subject": "Cloud Recording available: Product Strategy Sync",
        "snippet": "Your cloud recording from Sept 16 is now ready to view or download...",
        "labels": ["INBOX", "CATEGORY_UPDATES"],
        "date": "Wed, 16 Sep 2026 17:00:00 +0000",
        "internal_date_ms": _to_ms("2026-09-16 17:00:00"),
    },
]

# -------------------------------------------------------------------
# Full Email Bodies for Thread Inspection & Body Caching
# -------------------------------------------------------------------
MOCK_BODIES = {
    "em_01": (
        "Hey Alex,\n\n"
        "Wanted to kick off the discussion regarding our local storage choice for the new backend. "
        "We are debating between SQLite and DuckDB. Let me know your thoughts.\n\n"
        "Best,\nAlice"
    ),
    "em_02": (
        "Hi Alice,\n\n"
        "SQLite seems much lighter and has zero overhead for local desktop apps. "
        "It also has excellent FTS5 search support.\n\n"
        "Cheers,\nAlex"
    ),
    "em_03": (
        "Agreed! Final decision: we will proceed with SQLite and set the schema migration deadline to Oct 1st. "
        "Great points on FTS5.\n\nAlice"
    ),
    "em_04": (
        "Hi team,\n\n"
        "Due to client demos, sprint planning is moved to Monday at 10 AM PST. "
        "Please update your tickets before then.\n\nBob"
    ),
    "em_05": (
        "Quick reminder: Please bring your velocity estimates to the room or Zoom link.\n\nBob"
    ),
    "em_06": (
        "Your application for Senior AI Engineer was submitted to InnovateTech. "
        "We will notify you when the employer reviews it."
    ),
    "em_09": (
        "Hi Alex,\n\n"
        "I came across your profile and would love to invite you for an interview with FinTech Global "
        "for the Lead AI Systems Engineer role. Are you available for a 30-min call this Thursday?\n\n"
        "Best regards,\nSarah Jenkins\nRobert Walters"
    ),
    "em_10": (
        "Thank you for applying. We would like to schedule a 45-minute technical screen with an Anthropic Partner. "
        "Please select a time slot using the link provided."
    ),
    "em_13": (
        "alex-dev merged commit 8f19ac into main. 4 checks passed.\n"
        "Title: feat: add streaming support to llama client."
    ),
    "em_14": (
        "Issue #50: Memory leak during long context eval.\n"
        "When running 128k context windows, memory does not free up properly after stopping server."
    ),
    "em_15": (
        "Dependabot detected 1 moderate vulnerability in pyproject.toml.\n"
        "Bump requests from 2.31.0 to 2.32.0 in backend."
    ),
    "em_19": (
        "Receipt from Anthropic, PBC.\n"
        "Amount paid: $49.00 for Claude API Usage Tier 2.\n"
        "Date: September 1, 2026.\n"
        "Payment method: Mastercard ending in 1122."
    ),
    "em_22": (
        "Trip total: $18.50.\n"
        "Date: June 10, 2026.\n"
        "Pickup: Downtown Station. Dropoff: Residence.\n"
        "Payment: Apple Pay."
    ),
}


def seed_test_database(db: Database) -> None:
    """Populates the given Database instance with the 30 mock emails and cached bodies."""
    db.ingest_emails(MOCK_EMAILS)
    for email_id, body in MOCK_BODIES.items():
        # Find thread_id from MOCK_EMAILS
        thread_id = next(e["thread_id"] for e in MOCK_EMAILS if e["id"] == email_id)
        db.cache_email_body(email_id=email_id, thread_id=thread_id, body=body)
