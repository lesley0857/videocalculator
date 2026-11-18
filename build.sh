#!/usr/bin/env bash
set -e

# Render's build environment may not expose service settings consistently to
# every command. Keep collection, verification, migrations, and seeding aligned.
export DJANGO_SETTINGS_MODULE=videocalculatorproject.settings.production

python -m pip install -r requirements/production.txt
python manage.py shell -c 'import os; from django.conf import settings; from django.contrib.staticfiles.storage import staticfiles_storage; print("Django settings module:", os.environ["DJANGO_SETTINGS_MODULE"]); print("STATIC_ROOT:", settings.STATIC_ROOT); print("STATIC_URL:", settings.STATIC_URL); print("Configured static storage backend:", settings.STORAGES["staticfiles"]["BACKEND"]); print("Runtime static storage class:", staticfiles_storage.__class__.__module__ + "." + staticfiles_storage.__class__.__name__)'
python manage.py collectstatic --noinput
python manage.py verify_static_manifest
python manage.py migrate --noinput
python manage.py seed_initial_data --noinput
