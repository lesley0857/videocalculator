"""
Device management services.
Keep business logic out of views.
"""
from typing import Any, Optional
from .models import Device


def register_or_update_device(
    user: Any,
    device_fingerprint: str,
    user_agent: str = '',
    ip_address: Optional[str] = None,
) -> Device:
    """
    Registers a new device or updates last active metadata for an existing device.
    """
    device, _ = Device.objects.update_or_create(
        user=user,
        device_fingerprint=device_fingerprint,
        defaults={
            'user_agent': user_agent,
            'ip_address': ip_address,
        },
    )
    return device


def revoke_device(device: Device) -> None:
    """
    Revokes device authorization.
    """
    device.is_trusted = False
    device.save(update_fields=['is_trusted'])

