"""
Utility functions for the application.
"""
from datetime import datetime, date
from typing import Optional
from urllib.parse import urlparse


def safe_referrer(fallback_endpoint='records.index'):
    """
    Return request.referrer only if it points to the same host.
    Prevents open redirect attacks via manipulated Referer header.
    """
    from flask import request, url_for
    referrer = request.referrer
    if referrer:
        ref_parsed = urlparse(referrer)
        host_parsed = urlparse(request.host_url)
        if ref_parsed.netloc == host_parsed.netloc:
            return referrer
    return url_for(fallback_endpoint)


def escape_like(value: str) -> str:
    """Escape special LIKE/ILIKE characters (%, _) for safe use in SQL patterns."""
    return value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def get_user_map():
    """Return cached {user_id: username} mapping. Cleared together with dropdown cache."""
    try:
        from app.extensions import cache
        cached = cache.get('_user_map')
        if cached is not None:
            return cached
        from models import User
        user_map = {u.id: u.username for u in User.query.all()}
        cache.set('_user_map', user_map, timeout=300)
        return user_map
    except Exception:
        from models import User
        return {u.id: u.username for u in User.query.all()}


def validate_record_form(form_data: dict, require_status_and_dept: bool = False) -> tuple:
    """
    Validate record form data shared across add/edit routes.

    Args:
        form_data: dict-like object (e.g., request.form)
        require_status_and_dept: if True, discharge_department and discharge_status are required

    Returns:
        (parsed_data_dict, None) on success
        (None, error_message) on failure
    """
    date_str = form_data.get('date_of_discharge', '').strip()
    full_name = form_data.get('full_name', '').strip()
    discharge_department = form_data.get('discharge_department', '').strip()
    treating_physician = form_data.get('treating_physician', '').strip()
    history = form_data.get('history', '').strip()
    k_days_str = form_data.get('k_days', '').strip()
    discharge_status = form_data.get('discharge_status', '').strip()
    date_of_death_str = form_data.get('date_of_death', '').strip()
    comment = form_data.get('comment', '').strip()
    adsj = form_data.get('adsj', '').strip() if require_status_and_dept else ''
    suma_str = form_data.get('suma', '').strip() if require_status_and_dept else ''

    required = [date_str, full_name, treating_physician, history, k_days_str]
    if require_status_and_dept:
        required.extend([discharge_department, discharge_status])
    if not all(required):
        return None, "Будь ласка, заповніть усі обов'язкові поля"

    date_of_discharge = parse_date(date_str)
    if date_of_discharge is None:
        return None, 'Невірний формат дати виписки'

    k_days_int = parse_integer(k_days_str)
    if k_days_int is None:
        return None, '"К днів" повинно бути цілим числом'

    date_of_death = None
    if date_of_death_str:
        date_of_death = parse_date(date_of_death_str)
        if date_of_death is None:
            return None, 'Невірний формат дати смерті'
        if date_of_death < date_of_discharge:
            return None, 'Дата смерті не може бути раніше дати виписки'

    suma = parse_numeric(suma_str) if suma_str else None

    return {
        'date_of_discharge': date_of_discharge,
        'full_name': full_name,
        'discharge_department': discharge_department or None,
        'treating_physician': treating_physician,
        'history': history,
        'k_days': k_days_int,
        'discharge_status': discharge_status,
        'date_of_death': date_of_death,
        'comment': comment or None,
        'adsj': adsj or None,
        'suma': suma,
    }, None


def get_distinct_statuses():
    """Get distinct discharge statuses from database (cached)."""
    from app.extensions import cache
    from models import Record, db
    @cache.memoize(timeout=900)
    def _inner():
        return [s[0] for s in db.session.query(Record.discharge_status).distinct()
                .filter(Record.discharge_status != None)
                .order_by(Record.discharge_status).all()]
    return _inner()


def get_distinct_physicians():
    """Get distinct treating physicians from database (cached)."""
    from app.extensions import cache
    from models import Record, db
    @cache.memoize(timeout=900)
    def _inner():
        return [p[0] for p in db.session.query(Record.treating_physician).distinct()
                .filter(Record.treating_physician != None)
                .order_by(Record.treating_physician).all()]
    return _inner()


def get_distinct_departments():
    """Get distinct discharge departments from database (cached)."""
    from app.extensions import cache
    from models import Record, db
    @cache.memoize(timeout=900)
    def _inner():
        return [d[0] for d in db.session.query(Record.discharge_department).distinct()
                .filter(Record.discharge_department != None)
                .order_by(Record.discharge_department).all()]
    return _inner()


def clear_dropdown_cache():
    """
    Clear dropdown-related caches after adding/editing records.
    Uses targeted deletion instead of clearing the entire cache.
    """
    try:
        from app.extensions import cache
        cache.clear()
    except Exception:
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
