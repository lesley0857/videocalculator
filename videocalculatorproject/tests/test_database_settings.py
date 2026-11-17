import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_SCRIPT = (
    'import json; from videocalculatorproject.settings import production as s; '
    "db=s.DATABASES['default']; "
    "print(json.dumps({'engine': db['ENGINE'], 'name': db['NAME'], "
    "'host': db['HOST'], 'sslmode': db['OPTIONS'].get('sslmode')}))"
)


class DatabaseSettingsTests(unittest.TestCase):
    def run_settings(self, settings_module, **overrides):
        env = os.environ.copy()
        for name in ('DATABASE_URL', 'DB_NAME', 'DB_USER', 'DB_PASSWORD', 'DB_HOST', 'DB_PORT'):
            env.pop(name, None)
        env.update({
            'PYTHON_DOTENV_DISABLED': 'true',
            'DJANGO_SETTINGS_MODULE': settings_module,
            'ALLOWED_HOSTS': 'example.onrender.com',
            'SECRET_KEY': 'test-only-secret-key',
        })
        env.update(overrides)
        return subprocess.run(
            [sys.executable, '-c', SETTINGS_SCRIPT],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_production_loads_postgresql_url_and_defaults_ssl_to_required(self):
        result = self.run_settings(
            'videocalculatorproject.settings.production',
            DATABASE_URL='postgresql://test-user:test-password@db.example.invalid:5432/test-db',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads(result.stdout)
        self.assertEqual(config['engine'], 'django.db.backends.postgresql')
        self.assertEqual(config['name'], 'test-db')
        self.assertEqual(config['host'], 'db.example.invalid')
        self.assertEqual(config['sslmode'], 'require')

    def test_production_rejects_missing_or_empty_database_url_even_with_db_host(self):
        for url in (None, ''):
            with self.subTest(database_url='missing' if url is None else 'empty'):
                overrides = {'DB_HOST': 'localhost', 'DB_NAME': 'ignored'}
                if url is not None:
                    overrides['DATABASE_URL'] = url
                result = self.run_settings(
                    'videocalculatorproject.settings.production', **overrides
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('DATABASE_URL must be configured for production.', result.stderr)
                self.assertNotIn('localhost', result.stderr)

    def test_production_respects_explicit_sslmode(self):
        result = self.run_settings(
            'videocalculatorproject.settings.production',
            DATABASE_URL=(
                'postgresql://test-user:test-password@db.example.invalid:5432/test-db'
                '?sslmode=verify-full'
            ),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['sslmode'], 'verify-full')

    def test_development_defaults_to_sqlite(self):
        result = subprocess.run(
            [sys.executable, '-c', (
                'from videocalculatorproject.settings import development as s; '
                "print(s.DATABASES['default']['ENGINE'])"
            )],
            cwd=PROJECT_ROOT,
            env={**os.environ, 'PYTHON_DOTENV_DISABLED': 'true', 'USE_POSTGRES': 'False'},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'django.db.backends.sqlite3')

    def test_development_can_use_postgresql(self):
        result = subprocess.run(
            [sys.executable, '-c', (
                'from videocalculatorproject.settings import development as s; '
                "print(s.DATABASES['default']['ENGINE'])"
            )],
            cwd=PROJECT_ROOT,
            env={
                **os.environ,
                'PYTHON_DOTENV_DISABLED': 'true',
                'USE_POSTGRES': 'True',
                'DB_NAME': 'local-test-db',
                'DB_USER': 'local-test-user',
                'DB_PASSWORD': 'local-test-password',
                'DB_HOST': 'localhost',
                'DB_PORT': '5432',
            },
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'django.db.backends.postgresql')


if __name__ == '__main__':
    unittest.main()
