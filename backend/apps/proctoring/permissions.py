from django.conf import settings
from django.utils.crypto import constant_time_compare
from rest_framework.permissions import BasePermission

from .models import Student


class IsStudent(BasePermission):
    def has_permission(self, request, view) -> bool:
        return isinstance(request.user, Student)


class HasAdminKey(BasePermission):
    """Teacher/admin access via the `X-Admin-Key` header. Disabled unless ADMIN_API_KEY is set."""

    def has_permission(self, request, view) -> bool:
        expected = settings.ADMIN_API_KEY
        provided = request.headers.get("X-Admin-Key", "")
        return bool(expected) and constant_time_compare(provided, expected)
