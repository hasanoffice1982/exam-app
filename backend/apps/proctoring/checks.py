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
