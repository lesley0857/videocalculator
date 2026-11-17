"""
Production settings for videocalculatorproject.
"""

import os
from psycopg.conninfo import conninfo_to_dict
from django.core.exceptions import ImproperlyConfigured
from .base import *

DEBUG = False

# Allowed hosts MUST be set in production via environment variable
allowed_hosts_str = os.getenv('ALLOWED_HOSTS', '')
if not allowed_hosts_str:
    raise ValueError(
        "ALLOWED_HOSTS environment variable must be set in production.")
ALLOWED_HOSTS = [h.strip() for h in allowed_hosts_str.split(',') if h.strip()]

# Secret key MUST be explicitly provided from environment in production
secret_key_env = os.getenv('SECRET_KEY')
if not secret_key_env or secret_key_env.startswith('django-insecure'):
    raise ValueError(
        "A secure SECRET_KEY must be provided in production via environment variable.")
SECRET_KEY = secret_key_env

# Django's default production request handler emails errors to ADMINS and
# filters console output to DEBUG=True. Render needs request tracebacks on its
# captured stdout/stderr streams while DEBUG remains disabled.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'production': {
            'format': '{asctime} {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'INFO',
            'stream': 'ext://sys.stdout',
            'formatter': 'production',
        },
        'error_console': {
            'class': 'logging.StreamHandler',
            'level': 'ERROR',
            'stream': 'ext://sys.stderr',
            'formatter': 'production',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['error_console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['error_console'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}

# Production must use the PostgreSQL URL configured by the hosting environment.
database_url = os.getenv('DATABASE_URL')
if not database_url or not database_url.strip():
    raise ImproperlyConfigured(
        'DATABASE_URL must be configured for production.'
    )

database_options = conninfo_to_dict(database_url)
database_options.setdefault('sslmode', 'require')
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': database_options.pop('dbname', ''),
        'USER': database_options.pop('user', ''),
        'PASSWORD': database_options.pop('password', ''),
        'HOST': database_options.pop('host', ''),
        'PORT': database_options.pop('port', ''),
        'OPTIONS': database_options,
        'CONN_MAX_AGE': 600,
        'CONN_HEALTH_CHECKS': True,
    }
}

# Security hardening
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True

# Render terminates public TLS at its edge and forwards the original scheme.
# Trust the header only on Render so Django's HTTPS redirect and secure-cookie
# settings see the external request as HTTPS.
if os.getenv('RENDER_EXTERNAL_HOSTNAME'):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

if os.getenv('SECURE_SSL_REDIRECT', 'False').lower() in ('true', '1', 'yes'):
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', 31536000))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# Static files storage for production with WhiteNoise
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Production Email backend (SMTP or external service configured via env)
EMAIL_BACKEND = os.getenv(
    'EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST', '')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.getenv(
    'EMAIL_USE_TLS', 'True').lower() in ('true', '1', 'yes')
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv(
    'DEFAULT_FROM_EMAIL', 'noreply@videocalculator.com')
