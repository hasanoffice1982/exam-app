import hashlib

from django.utils import timezone
from rest_framework import authentication, exceptions

from .models import StudentToken


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class StudentTokenAuthentication(authentication.BaseAuthentication):
    """`Authorization: Bearer <token>` -> (Student, StudentToken) in a single query."""

    keyword = "Bearer"

    def authenticate_header(self, request) -> str:
        return self.keyword

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).split()
        if not header or header[0].decode().lower() != self.keyword.lower():
            return None
        if len(header) != 2:
            raise exceptions.AuthenticationFailed("Invalid token header.")

        token = (
            StudentToken.objects.select_related("student")
            .filter(key_hash=hash_token(header[1].decode(errors="ignore")))
            .first()
        )
        if token is None:
            raise exceptions.AuthenticationFailed("Invalid or revoked session.")
        if token.expires_at <= timezone.now():
            raise exceptions.AuthenticationFailed("Session expired.")
        if not token.student.is_active:
            raise exceptions.AuthenticationFailed("Account disabled.")
        return token.student, token
