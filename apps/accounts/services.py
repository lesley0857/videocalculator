"""
Account domain services.
All business logic is isolated here, out of views.
"""
from typing import Optional
from .models import User


def register_user(
    email: str,
    password: Optional[str] = None,
    first_name: str = '',
    last_name: str = '',
) -> User:
    """
    Registers a new user account with validated email identity.
    """
    return User.objects.create_user(
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
    )


def deactivate_user(user: User) -> User:
    """
    Safely deactivates a user account.
    """
    user.is_active = False
    user.save(update_fields=['is_active'])
    return user

