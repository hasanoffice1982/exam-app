from django.conf import settings
from django.core import checks


@checks.register()
def email_backend_check(app_configs, **kwargs):
    """Activation passwords are emailed; the console backend would silently print them into server logs."""
    if not settings.DEBUG and settings.EMAIL_BACKEND.endswith("console.EmailBackend"):
        return [
            checks.Warning(
                "Emails are printed to the server console, so students will not receive their passwords.",
                hint="Set EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend and the EMAIL_HOST* variables.",
                id="proctoring.W001",
            )
        ]
    return []


@checks.register()
def secret_key_check(app_configs, **kwargs):
    if not settings.DEBUG and settings.SECRET_KEY.startswith("dev-only-insecure"):
        return [
            checks.Warning(
                "DJANGO_SECRET_KEY is not set: sessions and signed data use the public development key.",
                hint="Set a long random DJANGO_SECRET_KEY (and DJANGO_DEBUG=0, DJANGO_ALLOWED_HOSTS) on the server.",
                id="proctoring.W002",
            )
        ]
    return []
