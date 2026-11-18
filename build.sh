#!/usr/bin/env bash
set -e

python -m pip install -r requirements/production.txt
python manage.py collectstatic --noinput
python manage.py migrate --noinput
python manage.py seed_initial_data --noinput
