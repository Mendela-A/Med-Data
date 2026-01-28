"""
Utility functions for the application.
"""
from datetime import datetime, date
from typing import Optional


def clear_dropdown_cache():
    """
    Clear all dropdown caches - call after adding/editing records.

    Note: This is a simplified version for blueprint compatibility.
    The full implementation with memoized cache clearing is in app.py.
    For now, we clear the entire cache to ensure data consistency.
    """
    try:
        from app.extensions import cache
        cache.clear()
    except Exception:
        # If cache is not available, silently pass
        # This allows blueprints to work even if cache is not initialized
        pass


def parse_date(date_str: str, default: Optional[date] = None) -> Optional[date]:
    """
    Parse date string in multiple formats.

    Supports formats:
    - dd.mm.yyyy (Ukrainian format)
    - yyyy-mm-dd (ISO format)

    Args:
        date_str: Date string to parse
        default: Default value to return if parsing fails (default: None)

    Returns:
        Parsed date object or default value if parsing fails

    Examples:
        >>> parse_date('31.12.2023')
        datetime.date(2023, 12, 31)
        >>> parse_date('2023-12-31')
        datetime.date(2023, 12, 31)
        >>> parse_date('invalid')
        None
    """
    if not date_str or not date_str.strip():
        return default

    date_str = date_str.strip()

    # Try multiple date formats
    formats = (
        '%d.%m.%Y',  # Ukrainian format: 31.12.2023
        '%Y-%m-%d',  # ISO format: 2023-12-31
    )

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue

    # If no format matched, return default
    return default


def parse_numeric(value_str: str, default: Optional[float] = None) -> Optional[float]:
    """
    Parse numeric value, handling both comma and dot as decimal separator.

    Args:
        value_str: Numeric string to parse (e.g., "123.45" or "123,45")
        default: Default value to return if parsing fails (default: None)

    Returns:
        Parsed float value or default if parsing fails

    Examples:
        >>> parse_numeric('123.45')
        123.45
        >>> parse_numeric('123,45')
        123.45
        >>> parse_numeric('invalid')
        None
    """
    if not value_str or not value_str.strip():
        return default

    value_str = value_str.strip().replace(',', '.')

    try:
        return float(value_str)
    except ValueError:
        return default


def parse_integer(value_str: str, default: Optional[int] = None) -> Optional[int]:
    """
    Parse integer value.

    Args:
        value_str: Integer string to parse
        default: Default value to return if parsing fails (default: None)

    Returns:
        Parsed integer value or default if parsing fails

    Examples:
        >>> parse_integer('42')
        42
        >>> parse_integer('invalid')
        None
    """
    if not value_str or not value_str.strip():
        return default

    value_str = value_str.strip()

    try:
        return int(value_str)
    except ValueError:
        return default
