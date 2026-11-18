import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase


class VerifyStaticManifestTests(SimpleTestCase):
    hashed_name = 'css/main.123456abcdef.css'

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.static_root = Path(self.temp_dir.name)
        self.hashed_file = self.static_root / self.hashed_name
        self.hashed_file.parent.mkdir(parents=True)
        self.hashed_file.write_text('body {}', encoding='utf-8')
        self.manifest_path = self.static_root / 'staticfiles.json'
        storage_patcher = patch(
            'apps.pricing.management.commands.verify_static_manifest.staticfiles_storage'
        )
        self.storage = storage_patcher.start()
        self.addCleanup(storage_patcher.stop)
        self.storage.url.return_value = f'/static/{self.hashed_name}'

    def write_manifest(self, filename=None, *, valid_paths=True):
        if valid_paths:
            manifest = {'paths': {'css/main.css': filename or self.hashed_name}}
        else:
            manifest = {'paths': []}
        self.manifest_path.write_text(json.dumps(manifest), encoding='utf-8')

    def run_command(self):
        with patch('apps.pricing.management.commands.verify_static_manifest.settings.STATIC_ROOT', self.static_root):
            call_command('verify_static_manifest')

    def test_valid_manifest_and_existing_hashed_file_pass(self):
        self.write_manifest()
        with patch('apps.pricing.management.commands.verify_static_manifest.settings.STATIC_ROOT', self.static_root):
            from io import StringIO

            output = StringIO()
            call_command('verify_static_manifest', stdout=output)
        self.assertIn('css/main.css', output.getvalue())
        self.assertIn(self.hashed_name, output.getvalue())
        self.assertIn('Hashed file exists: yes', output.getvalue())
        self.storage.url.assert_called_once_with('css/main.css')

    def test_missing_manifest_fails(self):
        with self.assertRaisesRegex(CommandError, 'does not exist'):
            self.run_command()

    def test_invalid_json_manifest_fails(self):
        self.manifest_path.write_text('{not json', encoding='utf-8')
        with self.assertRaisesRegex(CommandError, 'valid JSON'):
            self.run_command()

    def test_missing_required_key_fails(self):
        self.manifest_path.write_text(json.dumps({'paths': {}}), encoding='utf-8')
        with self.assertRaisesRegex(CommandError, 'missing the required entry'):
            self.run_command()

    def test_unhashed_or_invalid_manifest_filename_fails(self):
        for filename in ('css/main.css', 'css/main.latest.css', 'css/other.123456abcdef.css'):
            with self.subTest(filename=filename):
                self.write_manifest(filename)
                with self.assertRaisesRegex(CommandError, 'valid hashed filename'):
                    self.run_command()

    def test_missing_hashed_file_fails(self):
        self.hashed_file.unlink()
        self.write_manifest()
        with self.assertRaisesRegex(CommandError, 'does not exist'):
            self.run_command()

    def test_storage_url_resolution_failure_fails(self):
        self.write_manifest()
        self.storage.url.side_effect = ValueError('missing manifest entry')
        with self.assertRaisesRegex(CommandError, 'could not resolve'):
            self.run_command()

    def test_storage_url_for_different_file_fails(self):
        self.write_manifest()
        self.storage.url.return_value = '/static/css/main.differenthash.css'
        with self.assertRaisesRegex(CommandError, 'does not point to the manifest file'):
            self.run_command()

    def test_path_traversal_manifest_filename_fails(self):
        self.write_manifest('../css/main.123456abcdef.css')
        with self.assertRaisesRegex(CommandError, 'safe path'):
            self.run_command()

    def test_build_runs_verification_immediately_after_collectstatic(self):
        build_script = Path('build.sh').read_text(encoding='utf-8').splitlines()
        commands = [line.strip() for line in build_script if line.strip().startswith('python manage.py')]
        collect_index = commands.index('python manage.py collectstatic --noinput')
        self.assertEqual(commands[collect_index + 1], 'python manage.py verify_static_manifest')
