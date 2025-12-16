from pathlib import Path
import os

from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file
# Try multiple possible locations for .env file
env_paths = [
    BASE_DIR / ".env",  # In projectsite directory
    BASE_DIR.parent / ".env",  # In pulse directory
    Path.cwd() / ".env",  # Current working directory
]
for env_path in env_paths:
    if env_path.exists():
        load_dotenv(env_path)
        break

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
# Loaded from environment; see .env for local development.
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-x64c=gema!#i3_t2di48a6t%1whnrqu1ykge(my=3z1zj#5t0a",  # fallback for dev
)

# SECURITY WARNING: don't run with debug turned on in production!
# Set via environment variable; defaults to False.
DEBUG = os.environ.get("DJANGO_DEBUG", "False") == "True"

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "[::1]",
    "sherly-unnipped-superrespectably.ngrok-free.dev",
    "wiki-reported-remind-area.trycloudflare.com",
]

# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "pulse",
    "widget_tweaks",
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
]

CSRF_TRUSTED_ORIGINS = [
    "https://sherly-unnipped-superrespectably.ngrok-free.dev",
    "http://192.168.11.198:8000",  # local network
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "projectsite.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(BASE_DIR, "templates")],
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

WSGI_APPLICATION = "projectsite.wsgi.application"

# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "Asia/Manila"

USE_I18N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = (BASE_DIR / "static",)

# Media files (user uploads)
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Authentication settings
# Django allauth configuration
AUTHENTICATION_BACKENDS = [
    # Django's default authentication backend
    "django.contrib.auth.backends.ModelBackend",
    # Allauth's authentication backend
    "allauth.account.auth_backends.AuthenticationBackend",
]

# Site ID (required for allauth)
SITE_ID = 1

# Login/Logout URLs
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"  # Redirect to landing page after login
LOGOUT_REDIRECT_URL = "/accounts/login/"  # After logout, go back to login

# Allauth Account Settings
ACCOUNT_LOGOUT_REDIRECT_URL = "/"  # Where to redirect after logout
ACCOUNT_LOGOUT_ON_GET = True  # Logout immediately on GET request

# New-style login configuration (replaces deprecated ACCOUNT_AUTHENTICATION_METHOD)
ACCOUNT_LOGIN_METHODS = {"username", "email"}  # Allow login with username OR email

# New-style signup configuration.
# We do NOT ask for a username explicitly; allauth will auto-generate one
# (for social logins it can use data from the provider, e.g. Google).
# - "email*" means email is required for local signup
# - "password1*" and "password2*" enforce entering the password twice
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]

ACCOUNT_EMAIL_VERIFICATION = "optional"

# Social Account Settings (Google OAuth)
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": [
            "profile",
            "email",
        ],
        "AUTH_PARAMS": {
            "access_type": "online",
        },
        "OAUTH_PKCE_ENABLED": False,
    }
}

# Note: OAuth credentials are configured in the database via SocialApplication model
# Go to Django admin → Social applications → Add social application
# Provider: Google
# Client id: (from your .env file - GOOGLE_OAUTH_CLIENT_ID)
# Secret key: (from your .env file - GOOGLE_OAUTH_CLIENT_SECRET)
# Sites: Select your site

# Auto-create user profile when social account is connected
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_EMAIL_REQUIRED = True
# Email verification behavior for social accounts (Google)
SOCIALACCOUNT_EMAIL_VERIFICATION = "optional"

# Email Configuration
# For production, use SMTP backend:
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")  # Gmail SMTP server
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", 587))
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True") == "True"
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "Pulse <noreply@pulse.com>")

# Site URL for email verification links
SITE_URL = "https://sherly-unnipped-superrespectably.ngrok-free.dev"