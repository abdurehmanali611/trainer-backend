import os
from datetime import timedelta
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def env_bool(key: str, default: bool = False) -> bool:
    return env(key, str(default)).strip().lower() in ("1", "true", "yes", "on")


SECRET_KEY = env("SECRET_KEY", env("DJANGO_SECRET_KEY", "insecure-dev-key"))
JWT_SECRET = env("JWT_SECRET", SECRET_KEY)

DEBUG = env_bool("DEBUG", True)
ALLOWED_HOSTS = [h.strip() for h in env("ALLOWED_HOSTS", "*").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "apps.core",
    "apps.accounts",
    "apps.fitness",
    "apps.platform_billing",
    "apps.internal",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
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
        "DIRS": [],
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

DB_NAME = env("DB_NAME")
if DB_NAME:
    db_host = env("DB_HOST", "127.0.0.1")
    db_options: dict = {"charset": "utf8mb4"}
    if env_bool("DB_SSL", db_host not in ("localhost", "127.0.0.1", "::1")):
        db_options["ssl"] = {}
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": DB_NAME,
            "USER": env("DB_USER"),
            "PASSWORD": env("DB_PASSWORD"),
            "HOST": db_host,
            "PORT": env("DB_PORT", "3306"),
            "OPTIONS": db_options,
            "CONN_MAX_AGE": int(env("DB_CONN_MAX_AGE", "60")),
        }
    }
elif env("DATABASE_URL"):
    DATABASES = {"default": dj_database_url.config(default=env("DATABASE_URL"), conn_max_age=600)}
else:
    raise RuntimeError(
        "No database configured. Set DB_NAME (and DB_USER/DB_PASSWORD/DB_HOST/DB_PORT) "
        "or DATABASE_URL in BackEnd/.env before starting the trainer backend."
    )

AUTH_USER_MODEL = "accounts.Trainer"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Addis_Ababa"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "apps.core.auth.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.DefaultPagination",
    "PAGE_SIZE": 50,
}

from rest_framework_simplejwt.settings import api_settings as jwt_settings  # noqa: E402

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "SIGNING_KEY": JWT_SECRET,
    "VERIFYING_KEY": JWT_SECRET,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "TOKEN_OBTAIN_SERIALIZER": "apps.accounts.serializers.TrainerTokenSerializer",
}

CORS_ALLOW_ALL_ORIGINS = env_bool("CORS_ALLOW_ALL_ORIGINS", DEBUG)
CORS_ALLOWED_ORIGINS = [
    origin.strip() for origin in env("CORS_ALLOWED_ORIGINS", "").split(",") if origin.strip()
]
CSRF_TRUSTED_ORIGINS = [
    origin.strip() for origin in env("CSRF_TRUSTED_ORIGINS", "").split(",") if origin.strip()
]

# ---------------------------------------------------------------------------
# Email — console backend (prints to runserver console) when EMAIL_HOST empty
# ---------------------------------------------------------------------------
if env("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = env("EMAIL_HOST")
    EMAIL_PORT = int(env("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = env("EMAIL_HOST_USER")
    EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
    EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "Trainer <noreply@example.com>")

# Frontend deep-link base used in reset emails
TRAINER_APP_RESET_URL = env("TRAINER_APP_RESET_URL", "trainer://auth/reset")
CLIENT_APP_RESET_URL = env("CLIENT_APP_RESET_URL", "trainerclient://auth/reset")

# Internal service token used by the client gateway
SERVICE_TOKEN = env("SERVICE_TOKEN", "change-me-service-token")

# Exposed to the client gateway via internal endpoints if needed
CLOUDINARY_CLOUD_NAME = env("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_PRESET_NAME = env("CLOUDINARY_PRESET_NAME", "")

# Subscription grace: client keeps access between period start and end even if
# the invoice is still pending (they pay inside the window).
SUBSCRIPTION_LOCK_AT_END_DATE = True
