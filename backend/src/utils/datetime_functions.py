from datetime import datetime
from dateutil import parser as dateutil_parser
from dateutil.parser import ParserError
import re


def parse_date_from_str(date: str, output_format: str = "%Y-%m-%d") -> str:
    """
    Parse a date string in (almost) any common format and return it
    in a single unified format (default: YYYY-MM-DD).

    Handles:
      - ISO formats: 2024-01-15, 2024-01-15T10:30:00Z
      - US formats: 01/15/2024, 1/15/24
      - EU formats: 15-01-2024 (ambiguous cases default to month-first
        unless day > 12 makes it unambiguous)
      - Written formats: January 15, 2024 / 15 Jan 2024 / Jan 15th, 2024
      - Compact formats: 20240115
      - With ordinal suffixes: 1st, 2nd, 3rd, 21st, etc.
      - Relative/partial: "2024", "March 2024" (defaults missing parts)
      - Extra whitespace, surrounding text/punctuation noise

    Raises:
        ValueError: if the string cannot be parsed as a date at all.
    """
    if not date or not isinstance(date, str):
        raise ValueError(f"Invalid input: {date!r}")

    cleaned = date.strip()
    if not cleaned:
        raise ValueError("Empty date string")

    # Strip ordinal suffixes: "21st" -> "21", "3rd" -> "3"
    cleaned = re.sub(r'\b(\d{1,2})(st|nd|rd|th)\b', r'\1', cleaned, flags=re.IGNORECASE)

    # Normalize common separators/noise
    cleaned = cleaned.replace('_', '-').strip(' \t\n,;.')

    # Compact numeric format: 20240115 -> treat explicitly (dateutil can
    # sometimes misread 8-digit strings)
    if re.fullmatch(r'\d{8}', cleaned):
        try:
            dt = datetime.strptime(cleaned, "%Y%m%d")
            return dt.strftime(output_format)
        except ValueError:
            pass  # fall through to general parser

    # Try a set of explicit formats first (fast path, avoids ambiguity
    # issues in dateutil's fuzzy guessing for known patterns)
    explicit_formats = [
        "%Y-%m-%d", "%Y/%m/%d",
        "%m-%d-%Y", "%m/%d/%Y", "%m-%d-%y", "%m/%d/%y",
        "%d-%m-%Y", "%d/%m/%Y",
        "%B %d, %Y", "%b %d, %Y",
        "%d %B %Y", "%d %b %Y",
        "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
    ]
    for fmt in explicit_formats:
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.strftime(output_format)
        except ValueError:
            continue

    # Fall back to dateutil's flexible parser (handles free text, ISO
    # with timezone offsets, month names, fuzzy noise, etc.)
    try:
        # dayfirst=False -> assume US-style (month/day) when ambiguous,
        # flip this default if your data is predominantly non-US
        dt = dateutil_parser.parse(cleaned, dayfirst=False, fuzzy=True)
        return dt.strftime(output_format)
    except (ParserError, ValueError, OverflowError, TypeError) as e:
        raise ValueError(f"Could not parse date from string: {date!r}") from e