"""Application-wide constants."""
from zoneinfo import ZoneInfo

# DST-aware Kyiv timezone (UTC+2 winter / UTC+3 summer).
# Use datetime.now(KYIV_TZ) instead of hardcoded timezone(timedelta(hours=2)).
KYIV_TZ = ZoneInfo('Europe/Kyiv')

# User roles
ROLE_ADMIN = 'admin'
ROLE_EDITOR = 'editor'
ROLE_OPERATOR = 'operator'
ROLE_VIEWER = 'viewer'
ROLE_AMBULATORY = 'ambulatory'
VALID_ROLES = (ROLE_ADMIN, ROLE_EDITOR, ROLE_OPERATOR, ROLE_VIEWER, ROLE_AMBULATORY)

# Record discharge statuses
STATUS_PROCESSING = 'Опрацьовується'
STATUS_DISCHARGED = 'Виписаний'
STATUS_VIOLATIONS = 'Порушені вимоги'
STATUS_NO_EPISODE = 'Епізод відсутній'
STATUS_DECEASED   = 'Помер'
STATUS_NO_GROUP   = 'Без групи'

# NSZU statuses
NSZU_STATUS_IN_PROGRESS = 'В обробці'
NSZU_STATUS_PROCESSED = 'Опрацьовано'
NSZU_STATUS_PAID = 'Оплачено'
NSZU_STATUS_NOT_PAYABLE = 'Не підлягає оплаті'
NSZU_STATUSES = [
    NSZU_STATUS_IN_PROGRESS,
    NSZU_STATUS_PROCESSED,
    NSZU_STATUS_PAID,
    NSZU_STATUS_NOT_PAYABLE,
]

# Tab access control
TABS = {
    'records':        'Записи',
    'ambulatory':     'Амбулаторна доп.',
    'nszu':           'НСЗУ',
    'statistics':     'Статистика',
    'statisty':       'Форми 007/016',
    'reports':        'Звіти',
    'print_settings': 'Налаштування друку',
    'admin_panel':    'Адмін-панель',
}

DEFAULT_ROLE_TABS = {
    'ambulatory': ['ambulatory'],
    'operator':   ['records', 'ambulatory', 'reports'],
    'editor':     ['records', 'ambulatory', 'nszu', 'reports'],
    'viewer':     ['records', 'ambulatory', 'nszu', 'statistics', 'statisty', 'reports'],
    'admin':      list(TABS.keys()),
}

# Maps permission key → effective role for @role_required checks
PERM_EFFECTIVE_ROLE = {
    'nszu':           'viewer',
    'statisty':       'viewer',
    'statistics':     'viewer',
    'records':        'operator',
    'ambulatory':     'operator',
    'reports':        'operator',
    'print_settings': 'admin',
    'admin_panel':    'admin',
}

# Admin-blueprint view functions that belong to the "admin_panel" tab
# (user/department/status/audit management — everything not covered by a more specific tab below).
_ADMIN_PANEL_VIEWS = {
    'admin_users', 'admin_create_user', 'admin_edit_user', 'admin_delete_user',
    'admin_departments', 'admin_create_department', 'admin_edit_department', 'admin_delete_department',
    'admin_statuses', 'admin_create_status', 'admin_update_status',
    'admin_set_default_status', 'admin_toggle_status', 'admin_delete_status',
    'admin_audit',
}


def resolve_tab_key(endpoint):
    """Map a Flask endpoint (e.g. 'records.index') to its access-control tab key.

    Returns None for endpoints that aren't gated by a tab (e.g. auth.*), so
    @role_required callers outside the tab system are left untouched.
    """
    if not endpoint or '.' not in endpoint:
        return None
    bp, _, view = endpoint.partition('.')
    if bp in ('records', 'ambulatory', 'nszu'):
        return bp
    if bp == 'statisty':
        return 'print_settings' if view == 'print_settings_edit' else 'statisty'
    if bp == 'admin':
        if view == 'admin_statistics':
            return 'statistics'
        if 'report' in view:
            return 'reports'
        if view in _ADMIN_PANEL_VIEWS:
            return 'admin_panel'
    return None

# Ukrainian month names
UKRAINIAN_MONTHS = {
    1: 'Січень', 2: 'Лютий', 3: 'Березень', 4: 'Квітень',
    5: 'Травень', 6: 'Червень', 7: 'Липень', 8: 'Серпень',
    9: 'Вересень', 10: 'Жовтень', 11: 'Листопад', 12: 'Грудень',
}
