"""
Django settings for Boben.
Developed by Jhon Grover Longsud.

Accounts, sessions and OAuth (Google, GitHub, Facebook) live in the "accounts" app.
Secrets (Gemini key, Django secret key, OAuth client secrets) are read from the
.env file or real environment variables. They are never sent to the browser.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load variables from .env (if it exists) into os.environ.
load_dotenv(BASE_DIR / ".env")

# ---- Security ---------------------------------------------------------------
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() in ("1", "true", "yes")
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if h.strip()
]

# ---- Apps -------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "assistant",
    "accounts",
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

# ---- Database (accounts, profiles, sessions) ----------------------------------
# SQLite by default. Set DATABASE_PATH to keep the file somewhere else (for example a mounted disk).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("DATABASE_PATH", str(BASE_DIR / "db.sqlite3")),
    }
}

# ---- Authentication ---------------------------------------------------------------
AUTHENTICATION_BACKENDS = ["accounts.backends.EmailBackend"]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "accounts:login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---- Sessions and cookies -----------------------------------------------------------
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14        # "Remember me" keeps you signed in for 14 days
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"               # Lax is required so the browser keeps the session after an OAuth redirect
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_SAVE_EVERY_REQUEST = False

# Behind a proxy or on a host such as Render/Railway, set DJANGO_BEHIND_PROXY=True so Django
# sees the original https:// scheme (needed for correct OAuth redirect URLs).
if os.environ.get("DJANGO_BEHIND_PROXY", "False").lower() in ("1", "true", "yes"):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

# Public address of the site, used to build OAuth callback URLs, for example https://boben.example.com
# Leave empty in development: the address of the current request is used.
SITE_URL = os.environ.get("SITE_URL", "").strip().rstrip("/")

# ---- OAuth (client secrets stay on the server) -------------------------------------
# Client IDs are public, so the Google and GitHub ones are the defaults here (override them in .env if you like).
# Client SECRETS are never written in code: they must only come from .env or real environment variables.
# Facebook has no default: create an app at developers.facebook.com and set FACEBOOK_APP_ID and FACEBOOK_APP_SECRET.
OAUTH_PROVIDERS = {
    "google": {
        "client_id": os.environ.get("GOOGLE_CLIENT_ID", "1061823963628-ka7d5qf50kpjce9h16iagfa2lcdk8od0.apps.googleusercontent.com").strip(),
        "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET", "").strip(),
    },
    "github": {
        "client_id": os.environ.get("GITHUB_CLIENT_ID", "Ov23li8iymLHAGbprCYS").strip(),
        "client_secret": os.environ.get("GITHUB_CLIENT_SECRET", "").strip(),
    },
    "facebook": {
        "client_id": os.environ.get("FACEBOOK_APP_ID", "").strip(),
        "client_secret": os.environ.get("FACEBOOK_APP_SECRET", "").strip(),
    },
}
FACEBOOK_GRAPH_VERSION = os.environ.get("FACEBOOK_GRAPH_VERSION", "v25.0").strip()

# Profile picture limits
AVATAR_MAX_UPLOAD_BYTES = 3 * 1024 * 1024
AVATAR_SIZE = 256

# ---- Static files -----------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Manila"
USE_I18N = False
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---- Gemini -----------------------------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()
# Backup models, tried in order when the main one is busy (503), missing (404) or rate-limited (429).
GEMINI_FALLBACK_MODELS = [
    m.strip()
    for m in os.environ.get(
        "GEMINI_FALLBACK_MODELS", "gemini-3.5-flash-lite,gemini-2.5-flash,gemini-2.5-flash-lite"
    ).split(",")
    if m.strip()
]
# Final ordered list with no duplicates: main model first.
GEMINI_MODELS = list(dict.fromkeys([GEMINI_MODEL] + GEMINI_FALLBACK_MODELS))

# Limits so nobody can send huge requests with your free-tier key.
MAX_PROMPT_CHARS = 2000        # longest single message
MAX_HISTORY_MESSAGES = 12      # how many past messages we send for context
MAX_HISTORY_CHARS = 8000       # total characters of history we accept
