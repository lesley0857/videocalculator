import os
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ProductionLoggingTests(unittest.TestCase):
    def test_request_exception_traceback_is_written_to_stderr_with_debug_off(self):
        script = '''
import django
django.setup()
import logging
try:
    raise RuntimeError("synthetic logging verification failure")
except RuntimeError:
    logging.getLogger("django.request").exception("Synthetic request failed")
'''
        env = os.environ.copy()
        for name in ('DATABASE_URL', 'DB_NAME', 'DB_USER', 'DB_PASSWORD', 'DB_HOST', 'DB_PORT'):
            env.pop(name, None)
        env.update({
            'PYTHON_DOTENV_DISABLED': 'true',
            'DJANGO_SETTINGS_MODULE': 'videocalculatorproject.settings.production',
            'ALLOWED_HOSTS': 'example.onrender.com',
            'SECRET_KEY': 'test-only-secret-key',
            'DATABASE_URL': (
                'postgresql://test-user:test-password@db.example.invalid:5432/test-db'
            ),
        })
        result = subprocess.run(
            [sys.executable, '-c', script],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertIn('ERROR django.request: Synthetic request failed', result.stderr)
        self.assertIn('Traceback (most recent call last):', result.stderr)
        self.assertIn('RuntimeError: synthetic logging verification failure', result.stderr)

    def test_production_keeps_debug_disabled_and_routes_database_errors_to_stderr(self):
        script = '''
import django
django.setup()
from django.conf import settings
import logging
assert settings.DEBUG is False
try:
    raise RuntimeError("synthetic database logging verification failure")
except RuntimeError:
    logging.getLogger("django.db.backends").exception("Synthetic database failure")
'''
        env = os.environ.copy()
        for name in ('DATABASE_URL', 'DB_NAME', 'DB_USER', 'DB_PASSWORD', 'DB_HOST', 'DB_PORT'):
            env.pop(name, None)
        env.update({
            'PYTHON_DOTENV_DISABLED': 'true',
            'DJANGO_SETTINGS_MODULE': 'videocalculatorproject.settings.production',
            'ALLOWED_HOSTS': 'example.onrender.com',
            'SECRET_KEY': 'test-only-secret-key',
            'DATABASE_URL': (
                'postgresql://test-user:test-password@db.example.invalid:5432/test-db'
            ),
        })
        result = subprocess.run(
            [sys.executable, '-c', script],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('ERROR django.db.backends: Synthetic database failure', result.stderr)
        self.assertIn('Traceback (most recent call last):', result.stderr)


if __name__ == '__main__':
    unittest.main()
