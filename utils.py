"""
Utility functions for the application.
"""
import uuid
from datetime import datetime, date
from typing import Optional, Tuple
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


def parse_month_range(args, now=None):
    """Parse month/date-range query params → (from_date, to_date, selected_year, selected_month).

    Reads 'from_date'+'to_date' (YYYY-MM-DD) or 'month_filter' (YYYY-MM) from *args*.
    Both returned dates are inclusive date objects. Falls back to the current month.
    """
    import calendar as _cal
    from datetime import date, datetime, timezone, timedelta

    if now is None:
        from constants import KYIV_TZ
        now = datetime.now(KYIV_TZ)

    from_str  = args.get('from_date',    '').strip()
    to_str    = args.get('to_date',      '').strip()
    month_str = args.get('month_filter', '').strip()

    try:
        if from_str and to_str:
            fd = date.fromisoformat(from_str)
            td = date.fromisoformat(to_str)
            if fd > td:
                fd, td = td, fd
            return fd, td, fd.year, fd.month
        if month_str:
            parts = month_str.split('-')
            if len(parts) != 2:
                raise ValueError()
            year, month = int(parts[0]), int(parts[1])
            if not (1 <= month <= 12):
                raise ValueError()
            start = date(year, month, 1)
            end   = date(year, month, _cal.monthrange(year, month)[1])
            return start, end, year, month
    except (ValueError, TypeError):
        pass

    year, month = now.year, now.month
    start = date(year, month, 1)
    end   = date(year, month, _cal.monthrange(year, month)[1])
    return start, end, year, month


def normalize_ehealth_id(value: str) -> Optional[str]:
    """Canonical lowercase UUID ('d9a421c8-8efc-11f1-...') or None if not a UUID.

    Only the hyphenated 36-char form is accepted — a stray character pasted by
    hand must not silently turn into a different, valid-looking ID.
    """
    value = value.strip()
    if len(value) != 36:
        return None
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


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
    ehealth_str = form_data.get('patient_ehealth_id', '').strip() if require_status_and_dept else ''
    is_urgent_str = form_data.get('is_urgent', '').strip()
    history_submitted = form_data.get('history_submitted') == '1'

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

    if discharge_status:
        # Як і в амбулаторії: неактивні приймаємо, невідомі — ні;
        # порожній довідник — перевірку пропускаємо
        known = {s['name'] for s in get_status_options('records', include_inactive=True)}
        if known and discharge_status not in known:
            return None, f'Невідомий статус виписки: «{discharge_status}»'

    suma = parse_numeric(suma_str) if suma_str else None

    patient_ehealth_id = None
    if ehealth_str:
        patient_ehealth_id = normalize_ehealth_id(ehealth_str)
        if patient_ehealth_id is None:
            return None, ('ID пацієнта (ЕСОЗ) має бути у форматі '
                          'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx (36 символів)')

    is_urgent = True if is_urgent_str == 'urgent' else (False if is_urgent_str == 'planned' else None)

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
        'patient_ehealth_id': patient_ehealth_id,
        'is_urgent': is_urgent,
        'history_submitted': history_submitted,
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
    """Clear the entire in-memory cache after adding/editing records."""
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


def validate_ambulatory_form(form_data: dict, require_status: bool = False) -> tuple:
    """
    Validate ambulatory record form data.

    Args:
        form_data: dict-like object (e.g., request.form)
        require_status: if True, discharge_status is required

    Returns:
        (parsed_data_dict, None) on success
        (None, error_message) on failure
    """
    date_str = form_data.get('date', '').strip()
    journal_number = form_data.get('journal_number', '').strip()
    full_name = form_data.get('full_name', '').strip()
    birth_date_str = form_data.get('birth_date', '').strip()
    doctor = form_data.get('doctor', '').strip()
    diagnosis = form_data.get('diagnosis', '').strip()
    discharge_status = form_data.get('discharge_status', '').strip()
    comment = form_data.get('comment', '').strip()
    is_urgent = form_data.get('is_urgent') in [True, 'true', '1', 'on']

    required = [date_str, journal_number, full_name, birth_date_str, doctor, diagnosis]
    if require_status:
        required.append(discharge_status)
    if not all(required):
        return None, "Будь ласка, заповніть усі обов'язкові поля"

    date_val = parse_date(date_str)
    if date_val is None:
        return None, 'Невірний формат дати'

    birth_date_val = parse_date(birth_date_str)
    if birth_date_val is None:
        return None, 'Невірний формат дати народження'

    if birth_date_val > date_val:
        return None, 'Дата народження не може бути пізніше дати запису'

    if discharge_status:
        # Приймаємо і неактивні статуси: редагування старого запису з
        # деактивованим статусом не повинно блокуватись. Порожній довідник
        # (init-db без seed) — перевірку пропускаємо.
        known = {s['name'] for s in get_ambulatory_statuses(include_inactive=True)}
        if known and discharge_status not in known:
            return None, f'Невідомий статус виписки: «{discharge_status}»'

    return {
        'date': date_val,
        'journal_number': journal_number,
        'full_name': full_name,
        'birth_date': birth_date_val,
        'doctor': doctor,
        'diagnosis': diagnosis,
        'discharge_status': discharge_status or None,
        'comment': comment or None,
        'is_urgent': is_urgent,
    }, None


# Fallback-статуси за замовчуванням, якщо довідник порожній (init-db без seed)
_FALLBACK_DEFAULT_STATUS = {
    'ambulatory': 'Опрацьовується',
    'records': 'Опрацьовується',
    'nszu': 'В обробці',
}


def get_status_options(scope='ambulatory', include_inactive=False):
    """Довідник статусів (таблиця status_options) як список dict-ів,
    впорядкований за sort_order. Кешується; інвалідація — clear_dropdown_cache()."""
    from app.extensions import cache
    from models import StatusOption

    @cache.memoize(timeout=900)
    def _inner(scope, include_inactive):
        q = StatusOption.query.filter_by(scope=scope)
        if not include_inactive:
            q = q.filter_by(is_active=True)
        rows = q.order_by(StatusOption.sort_order, StatusOption.name).all()
        return [{
            'id': s.id, 'name': s.name, 'color': s.color, 'icon': s.icon,
            'sort_order': s.sort_order, 'is_default': s.is_default,
            'is_active': s.is_active, 'show_in_stats': s.show_in_stats,
            'is_system': s.is_system,
        } for s in rows]
    return _inner(scope, include_inactive)


def get_default_status(scope='ambulatory'):
    """Назва статусу за замовчуванням для нових записів у scope."""
    statuses = get_status_options(scope)
    for s in statuses:
        if s['is_default']:
            return s['name']
    if statuses:
        return statuses[0]['name']
    return _FALLBACK_DEFAULT_STATUS.get(scope, 'Опрацьовується')


def get_ambulatory_statuses(include_inactive=False):
    return get_status_options('ambulatory', include_inactive)


def get_default_ambulatory_status():
    return get_default_status('ambulatory')


def get_distinct_ambulatory_doctors():
    """Get distinct doctors from database for ambulatory records (cached)."""
    from app.extensions import cache
    from models import AmbulatoryRecord, db
    @cache.memoize(timeout=900)
    def _inner():
        return [d[0] for d in db.session.query(AmbulatoryRecord.doctor).distinct()
                .filter(AmbulatoryRecord.doctor != None)
                .order_by(AmbulatoryRecord.doctor).all()]
    return _inner()


def get_distinct_nszu_doctors():
    """Get distinct doctors from NSZU corrections table (cached)."""
    from app.extensions import cache
    from models import NSZUCorrection, db
    @cache.memoize(timeout=900)
    def _inner():
        return [d[0] for d in db.session.query(NSZUCorrection.doctor).distinct()
                .filter(NSZUCorrection.doctor != None)
                .order_by(NSZUCorrection.doctor).all()]
    return _inner()


def get_distinct_audit_actions():
    """Get distinct audit action strings (cached 1 h — actions change infrequently)."""
    from app.extensions import cache
    from models import Audit, db
    @cache.memoize(timeout=3600)
    def _inner():
        return [a[0] for a in db.session.query(Audit.action).distinct()
                .order_by(Audit.action).all()]
    return _inner()


def clamp_per_page(value, default: int = 100, min_v: int = 10, max_v: int = 200) -> int:
    """Parse and clamp a per_page query/form value to [min_v, max_v]."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        v = default
    return max(min_v, min(v, max_v))


def autosize_columns(ws, max_width: int = 50) -> None:
    """Auto-size all columns in an openpyxl worksheet, capped at max_width."""
    from openpyxl.utils import get_column_letter
    for i, col in enumerate(ws.columns, 1):
        max_len = max(
            (len(str(cell.value)) for cell in col if cell.value is not None),
            default=0,
        )
        ws.column_dimensions[get_column_letter(i)].width = min(max_len + 2, max_width)


def parse_export_date_range(form, redirect_url: str) -> Tuple[Optional[date], object]:
    """Parse month/date-range from a POST form for export/print handlers.

    Returns (from_d, to_d) on success.
    Returns (None, redirect_response) on validation failure (flash already set).
    """
    from flask import flash, redirect
    import calendar as _cal

    export_mode = form.get('export_mode', 'month').strip()

    if export_mode == 'range':
        from_str = form.get('from_date', '').strip()
        to_str   = form.get('to_date',   '').strip()
        if not from_str or not to_str:
            flash('Будь ласка, вкажіть обидві дати для експорту', 'warning')
            return None, redirect(redirect_url)
        try:
            from_d = date.fromisoformat(from_str)
            to_d   = date.fromisoformat(to_str)
        except ValueError:
            flash('Невірний формат дати', 'warning')
            return None, redirect(redirect_url)
        if from_d > to_d:
            flash('Дата "з" не може бути пізніше дати "по"', 'warning')
            return None, redirect(redirect_url)
        return from_d, to_d

    # month mode
    month_str = form.get('month_filter', '').strip()
    if not month_str:
        flash('Будь ласка, вкажіть місяць для експорту', 'warning')
        return None, redirect(redirect_url)
    try:
        parts = month_str.split('-')
        if len(parts) != 2:
            raise ValueError()
        year, month = int(parts[0]), int(parts[1])
        if not (1 <= month <= 12):
            raise ValueError()
        from_d = date(year, month, 1)
        to_d   = date(year, month, _cal.monthrange(year, month)[1])
        return from_d, to_d
    except (ValueError, TypeError):
        flash('Невірний формат місяця (очікується YYYY-MM)', 'warning')
        return None, redirect(redirect_url)
