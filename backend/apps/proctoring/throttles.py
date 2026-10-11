from django.core.cache import cache
from rest_framework.throttling import BaseThrottle

HONEYPOT_FIELD = "website"  # hidden form field; humans never fill it
HONEYPOT_BLOCK_SECONDS = 60 * 60


def client_ip(request) -> str:
    return request.META.get("REMOTE_ADDR", "unknown")


def honeypot_key(request) -> str:
    return f"honeypot:{client_ip(request)}"


def trip_honeypot(request) -> bool:
    """True (and blocks the caller's IP) when the hidden field was filled in."""
    if request.data.get(HONEYPOT_FIELD):
        cache.set(honeypot_key(request), 1, HONEYPOT_BLOCK_SECONDS)
        return True
    return False


class HoneypotBlockThrottle(BaseThrottle):
    """Rejects IPs that previously filled the honeypot field."""

    def allow_request(self, request, view) -> bool:
        return cache.get(honeypot_key(request)) is None
