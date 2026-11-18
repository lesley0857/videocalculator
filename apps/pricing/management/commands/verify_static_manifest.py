"""Verify that the collected production CSS can be resolved from its manifest."""

import json
import re
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.management.base import BaseCommand, CommandError


REQUIRED_KEY = 'css/main.css'


class Command(BaseCommand):
    help = 'Verify the collected static manifest and the required main stylesheet.'

    def handle(self, *args, **options):
        try:
            static_root = Path(settings.STATIC_ROOT).resolve()
        except (TypeError, OSError) as exc:
            raise CommandError(f'Could not resolve STATIC_ROOT: {exc}') from exc
        manifest_path = static_root / 'staticfiles.json'
        if not manifest_path.is_file():
            raise CommandError(f'Static files manifest does not exist: {manifest_path}')
        try:
            manifest_path.resolve().relative_to(static_root)
        except (OSError, ValueError) as exc:
            raise CommandError(f'Static manifest path resolves outside STATIC_ROOT: {manifest_path}') from exc

        try:
            with manifest_path.open(encoding='utf-8') as manifest_file:
                manifest = json.load(manifest_file)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CommandError(f'Could not read a valid JSON static manifest at {manifest_path}: {exc}') from exc

        if not isinstance(manifest, dict) or not isinstance(manifest.get('paths'), dict):
            raise CommandError(f'Static manifest at {manifest_path} must contain a "paths" object.')
        paths = manifest['paths']
        if REQUIRED_KEY not in paths:
            raise CommandError(f'Static manifest is missing the required entry {REQUIRED_KEY!r}.')

        hashed_name = paths[REQUIRED_KEY]
        relative_path = self._validate_hashed_name(hashed_name)

        resolved_file = (static_root / Path(*relative_path.parts)).resolve()
        try:
            resolved_file.relative_to(static_root)
        except ValueError as exc:
            raise CommandError(f'Manifest path {hashed_name!r} resolves outside STATIC_ROOT.') from exc
        if not resolved_file.is_file():
            raise CommandError(f'Hashed static file from the manifest does not exist: {resolved_file}')

        try:
            static_url = staticfiles_storage.url(REQUIRED_KEY)
            url_path = unquote(urlsplit(static_url).path)
        except Exception as exc:
            raise CommandError(f'Django static storage could not resolve {REQUIRED_KEY!r}: {exc}') from exc
        if not (url_path == hashed_name or url_path.endswith('/' + hashed_name)):
            raise CommandError(
                f'Django resolved {REQUIRED_KEY!r} to {static_url!r}, which does not point to '
                f'the manifest file {hashed_name!r}.'
            )

        self.stdout.write(self.style.SUCCESS(
            'Static manifest verification passed.\n'
            f'Manifest: {manifest_path}\n'
            f'Static key: {REQUIRED_KEY}\n'
            f'Hashed file: {hashed_name}\n'
            f'Static URL: {static_url}\n'
            f'Hashed file exists: yes ({resolved_file})'
        ))

    @staticmethod
    def _validate_hashed_name(value):
        if not isinstance(value, str) or not value:
            raise CommandError(f'Manifest entry {REQUIRED_KEY!r} must be a hashed relative filename.')
        if '\\' in value:
            raise CommandError(f'Manifest filename {value!r} must use safe relative POSIX path syntax.')

        path = PurePosixPath(value)
        if path.is_absolute() or ':' in value or any(part in ('', '.', '..') for part in path.parts):
            raise CommandError(f'Manifest filename {value!r} is not a safe path inside STATIC_ROOT.')

        original = PurePosixPath(REQUIRED_KEY)
        hashed_stem = re.fullmatch(re.escape(original.stem) + r'\.[0-9a-fA-F]{8,}', path.stem)
        if (path.parent != original.parent or path.suffix != original.suffix or not hashed_stem
                or value == REQUIRED_KEY):
            raise CommandError(
                f'Manifest entry {REQUIRED_KEY!r} is not a valid hashed filename: {value!r}.'
            )
        return path
