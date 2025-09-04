"""
Django settings for smart-recipe-app
Ready for local dev and Render.com deployment.
"""

from pathlib import Path
import os
import dj_database_url
from dotenv import load_dotenv

# ---------------------------------------------------------------------
# BASE & ENV
# ---------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv()  # loads .env from project root

# ---------------------------------------------------------------------
# SECURITY
# ---------------------------------------------------------------------
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-secret")
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

ALLOWED_HOSTS = [
    x.strip()
    for x in os.getenv("ALLOWED_HOSTS", "127.0.0.1,localhost,.onrender.com").split(",")
    if x.strip()
]

CSRF_TRUSTED_ORIGINS = [
    x.strip()
    for x in os.getenv(
        "CSRF_TRUSTED_ORIGINS",
        "http://127.0.0.1:8000,http://localhost:8000,https://*.onrender.com",
    ).split(",")
    if x.strip()
]

# Correct scheme/host when behind Render’s proxy
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

# ---------------------------------------------------------------------
# APPS
# ---------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # third-party
    "rest_framework",

    # local
    "core",
    "accounts", 
]

# ---------------------------------------------------------------------
# MIDDLEWARE
# ---------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # after SecurityMiddleware
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# ---------------------------------------------------------------------
# URLS / WSGI
# ---------------------------------------------------------------------
ROOT_URLCONF = "config.urls"               # adjust if your project module is different
WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------
# TEMPLATES  (needed for admin & your own templates)
# ---------------------------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # put your HTML templates in BASE_DIR / "templates"
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,  # loads templates inside each app's /templates folder
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------------------------------------------------------------------
# DATABASE
# - Postgres on Render via DATABASE_URL
# - Falls back to SQLite locally if DATABASE_URL not provided
# ---------------------------------------------------------------------
db_from_env = dj_database_url.config(conn_max_age=600, ssl_require=True)
DATABASES = (
    {"default": db_from_env}
    if db_from_env
    else {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
)

# ---------------------------------------------------------------------
# PASSWORD VALIDATION
# ---------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------
# I18N / TZ
# ---------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------
# STATIC & MEDIA
# ---------------------------------------------------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]  # your source static assets (optional)
STATIC_ROOT = BASE_DIR / "staticfiles"    # collectstatic destination on Render
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---------------------------------------------------------------------
# LOGGING (show errors in Render logs)
# ---------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO"},
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}

# ---------------------------------------------------------------------
# Authentication redirects
# ---------------------------------------------------------------------
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "home"

# ---------------------------------------------------------------------
# Default primary key field type
# ---------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

ENABLE_AI_IMAGES = os.getenv("ENABLE_AI_IMAGES", "false").lower() in ("1", "true", "yes")

