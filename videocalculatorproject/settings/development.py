"""
Development settings for videocalculatorproject.
"""

import os
from .base import *

DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 'yes')

ALLOWED_HOSTS = [host.strip() for host in os.getenv(
    'ALLOWED_HOSTS', 'videocalculator.onrender.com,localhost,127.0.0.1,0.0.0.0').split(',') if host.strip()]

# Database configuration:
# Defaults safely to SQLite for seamless local onboarding if PostgreSQL is not active.
# Set USE_POSTGRES=True in .env to connect to local/remote PostgreSQL.
USE_POSTGRES = os.getenv(
    'USE_POSTGRES', 'False').lower() in ('true', '1', 'yes')

if USE_POSTGRES:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DB_NAME', 'videocalculator_dev'),
            'USER': os.getenv('DB_USER', 'postgres'),
            'PASSWORD': os.getenv('DB_PASSWORD', 'postgres'),
            'HOST': os.getenv('DB_HOST', 'localhost'),
            'PORT': os.getenv('DB_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Email backend for development - print to console
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
