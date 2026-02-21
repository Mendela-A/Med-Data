"""Application-wide constants."""

# User roles
ROLE_ADMIN = 'admin'
ROLE_EDITOR = 'editor'
ROLE_OPERATOR = 'operator'
ROLE_VIEWER = 'viewer'
VALID_ROLES = (ROLE_ADMIN, ROLE_EDITOR, ROLE_OPERATOR, ROLE_VIEWER)

# Record discharge statuses
STATUS_PROCESSING = 'Опрацьовується'
STATUS_DISCHARGED = 'Виписаний'
STATUS_VIOLATIONS = 'Порушені вимоги'

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

# Ukrainian month names
UKRAINIAN_MONTHS = {
    1: 'Січень', 2: 'Лютий', 3: 'Березень', 4: 'Квітень',
    5: 'Травень', 6: 'Червень', 7: 'Липень', 8: 'Серпень',
    9: 'Вересень', 10: 'Жовтень', 11: 'Листопад', 12: 'Грудень',
}
