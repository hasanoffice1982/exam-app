import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.proctoring",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# SQLite for the MVP; swap ENGINE/NAME/etc. for Postgres later.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "")  # enables POST /api/config/<id>/ via X-Admin-Key
STUDENT_TOKEN_TTL_HOURS = int(os.environ.get("STUDENT_TOKEN_TTL_HOURS", "8"))

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.proctoring.authentication.StudentTokenAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["apps.proctoring.permissions.IsStudent"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_THROTTLE_RATES": {
        "auth": "20/min",  # per IP, login + activate
        "events": "300/min",  # per student; offline queue flushes can burst
        "uploads": "60/min",
        "heartbeat": "10/min",
        "account": "30/min",  # profile, change password, logout (per student)
    },
}

# Throttle/lockout counters live in the cache. LocMem is per-process: use Redis if you run several workers.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# Screenshots can be several MB.
DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024

# Email: prints to the backend console in dev. Set EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
# plus the EMAIL_HOST* variables below to send real emails.
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_FILE_PATH = os.environ.get("EMAIL_FILE_PATH")  # for EMAIL_BACKEND=...filebased.EmailBackend (dev: emails as files)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "1") == "1"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "exams@localhost")

LOGIN_URL = "/admin/login/"

# Google Drive (or any) link to the student installer; shown on the home page when set.
STUDENT_DOWNLOAD_URL_MAC = os.environ.get("STUDENT_DOWNLOAD_URL_MAC", "")

# True: students activate themselves and the password is emailed. False: only teachers/admins hand out passwords.
SELF_ACTIVATION = os.environ.get("SELF_ACTIVATION", "1") == "1"
