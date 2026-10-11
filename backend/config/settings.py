import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "jazzmin",  # must come before django.contrib.admin
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
        "NAME": os.environ.get("DATABASE_PATH", BASE_DIR / "db.sqlite3"),
        "OPTIONS": {
            "timeout": 20,  # wait for a busy lock instead of failing: 20 students write at the same time
            "transaction_mode": "IMMEDIATE",
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
        },
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("TIME_ZONE", "UTC")  # e.g. Asia/Dhaka; also the zone teachers type times in
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", BASE_DIR / "media"))

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

LOGIN_URL = "/teacher/login/"
LOGIN_REDIRECT_URL = "/admin/"  # admin login without a ?next= lands in the admin; the teacher login sets its own target

# Google Drive (or any) link to the student installer; shown on the home page when set.
STUDENT_DOWNLOAD_URL_MAC = os.environ.get("STUDENT_DOWNLOAD_URL_MAC", "")

# True: students activate themselves and the password is emailed. False: only teachers/admins hand out passwords.
SELF_ACTIVATION = os.environ.get("SELF_ACTIVATION", "1") == "1"

# ---- Admin look (django-jazzmin): light "minty" teal theme, flat, no shadows, no animation ----
JAZZMIN_SETTINGS = {
    "site_title": "ExamProctor admin",
    "site_header": "ExamProctor",
    "site_brand": "ExamProctor",
    "site_logo": "proctoring/logo-flat.png",
    "login_logo": "proctoring/logo-flat.png",
    "site_icon": "proctoring/logo-flat.png",
    "site_logo_classes": "img-circle",
    "welcome_sign": "ExamProctor administration",
    "copyright": "ExamProctor",
    "search_model": ["proctoring.Student", "proctoring.Exam"],
    "user_avatar": None,
    "topmenu_links": [{"name": "Home", "url": "admin:index", "permissions": ["auth.view_user"]}],
    "show_sidebar": True,
    "navigation_expanded": True,
    "order_with_respect_to": [
        "proctoring.exam", "proctoring.examattempt", "proctoring.student", "proctoring.studenttoken",
        "proctoring.proctorevent", "proctoring.proctorscreenshot", "proctoring.consent", "auth",
    ],
    "icons": {
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user-tie",
        "auth.group": "fas fa-users",
        "proctoring.exam": "fas fa-file-alt",
        "proctoring.examattempt": "fas fa-tasks",
        "proctoring.student": "fas fa-user-graduate",
        "proctoring.studenttoken": "fas fa-key",
        "proctoring.proctorevent": "fas fa-stream",
        "proctoring.proctorscreenshot": "fas fa-image",
        "proctoring.consent": "fas fa-check-circle",
        "proctoring.batchchange": "fas fa-exchange-alt",
    },
    "default_icon_parents": "fas fa-folder",
    "default_icon_children": "fas fa-circle",
    "related_modal_active": False,
    "custom_css": "proctoring/admin-flat.css",
    "use_google_fonts_cdn": False,  # no external requests: the server may be on an offline school network
    "show_ui_builder": False,
    "changeform_format": "horizontal_tabs",
    "changeform_format_overrides": {"proctoring.exam": "single", "proctoring.student": "single"},
}
JAZZMIN_UI_TWEAKS = {
    "theme": "minty",
    "dark_mode_theme": None,
    "navbar": "navbar-white navbar-light",
    "no_navbar_border": True,
    "navbar_fixed": False,
    "sidebar": "sidebar-light-teal",
    "sidebar_fixed": True,
    "sidebar_nav_flat_style": True,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_child_indent": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_small_text": False,
    "accent": "accent-teal",
    "brand_colour": False,
    "body_small_text": False,
    "footer_small_text": True,
    "layout_boxed": False,
    "actions_sticky_top": False,
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-outline-secondary",
        "info": "btn-outline-info",
        "warning": "btn-outline-warning",
        "danger": "btn-outline-danger",
        "success": "btn-success",
    },
}
