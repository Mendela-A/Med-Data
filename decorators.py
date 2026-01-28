"""
Custom decorators for role-based access control
"""
from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user


def role_required(*roles):
    """
    Decorator to require specific role(s). Admin always has access unless explicitly excluded.

    Args:
        *roles: Variable number of role strings (e.g., 'operator', 'editor', 'admin', 'viewer')

    Returns:
        Decorated function that checks user role before executing

    Example:
        @role_required('admin', 'editor')
        def admin_function():
            pass
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            user_role = getattr(current_user, 'role', None)
            # admin has all rights (unless roles explicitly exclude it)
            allowed_roles = list(roles)
            if 'admin' not in allowed_roles and user_role == 'admin':
                allowed_roles.append('admin')
            if user_role not in allowed_roles:
                flash('Доступ заборонено', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator
