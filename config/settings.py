"""
Django settings for smart-recipe-app
Ready for local dev and Render.com deployment.
"""

from pathlib import Path
import os
import warnings
import dj_database_url
from dotenv import load_dotenv


# ---------------------------------------------------------------------
# BASE & ENV
# ---------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")  # loads .env from project root

# ---------------------------------------------------------------------
# OPENAI
# ---------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ---------------------------------------------------------------------
# Tesseract
# ---------------------------------------------------------------------
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

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

# --- Production security hardening ---
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = "Lax"
    CSRF_COOKIE_SAMESITE = "Lax"

    # HTTP Strict Transport Security (HSTS)
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    # Extra hardening (nice to have)
    SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
    X_FRAME_OPTIONS = "DENY"


# Correct scheme/host when behind Render’s proxy
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

# to print emails to the console.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

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
    "widget_tweaks",
]

# ---------------------------------------------------------------------
# MIDDLEWARE
# ---------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
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
ROOT_URLCONF = "config.urls"  # adjust if your project module is different
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
db_from_env = dj_database_url.config(default=None, conn_max_age=600, ssl_require=True)

if db_from_env:
    DATABASES = {"default": db_from_env}
else:
    warnings.warn("No DATABASE_URL set; falling back to local sqlite3.")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# ---------------------------------------------------------------------
# PASSWORD VALIDATION
# ---------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
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
STATIC_ROOT = BASE_DIR / "staticfiles"  # collectstatic destination on Render
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
WHITENOISE_AUTOREFRESH = False
WHITENOISE_USE_FINDERS = False
WHITENOISE_MAX_AGE = 31536000


MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Toggle S3
USE_S3 = os.getenv("USE_S3", "") == "1"

if USE_S3:

    INSTALLED_APPS += ["storages"]

    DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"

    AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME")
    AWS_S3_REGION_NAME = os.getenv("AWS_S3_REGION_NAME", "eu-north-1")
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")

    AWS_QUERYSTRING_AUTH = False  # public, cacheable URLs
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None
    # Optional helpers:
    # AWS_S3_ADDRESSING_STYLE = "virtual"
    AWS_S3_SIGNATURE_VERSION = "s3v4"

    # Public S3 base URL for media
    MEDIA_URL = (
        f"https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/"
    )

AWS_S3_CUSTOM_DOMAIN = os.getenv("AWS_S3_CUSTOM_DOMAIN")
if AWS_S3_CUSTOM_DOMAIN:
    MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/"


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
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}

# ---------------------------------------------------------------------
# Authentication redirects
# ---------------------------------------------------------------------
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "core:home"

# ---------------------------------------------------------------------
# Default primary key field type
# ---------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

ENABLE_AI_IMAGES = os.getenv("ENABLE_AI_IMAGES", "false").lower() in (
    "1",
    "true",
    "yes",
)
