from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connections
from django.test import TestCase
from decimal import Decimal

from apps.accounts.models import User
from apps.pricing.models import CostEstimate, ModelPricing, ProductionTool, SubscriptionPlan
from apps.video_registry.models import (
    AccessRoute, Capability, Evidence, Provider, ProviderOffering, Specialty, VideoModel,
)
from apps.workspace.models import Project


class SeedInitialDataTests(TestCase):
    def test_repeated_run_seeds_researched_catalogue_without_touching_existing_data(self):
        user = User.objects.create_user(email='existing@example.test', password='test-password')
        project = Project.objects.create(owner=user, name='Existing project')
        estimate = CostEstimate.objects.create(owner=user, project=project, inputs={'keep': True}, result={'total': 10})

        call_command('seed_initial_data', noinput=True, stdout=StringIO())
        plan = SubscriptionPlan.objects.get(slug='chatgpt-plus-us')
        self.assertEqual(plan.subscription_price, Decimal('20.00000000'))
        SubscriptionPlan.objects.filter(pk=plan.pk).update(subscription_price='123.00000000', is_active=True)

        models = (Specialty, Provider, ProviderOffering, SubscriptionPlan, VideoModel, AccessRoute,
                  Capability, Evidence, ModelPricing, ProductionTool)
        first_counts = [model.objects.count() for model in models]
        call_command('seed_initial_data', noinput=True, stdout=StringIO())

        self.assertEqual([model.objects.count() for model in models], first_counts)
        plan.refresh_from_db()
        self.assertEqual(plan.subscription_price, Decimal('123.00000000'))
        self.assertTrue(plan.is_active)
        self.assertEqual(User.objects.get(pk=user.pk).email, 'existing@example.test')
        self.assertEqual(Project.objects.get(pk=project.pk).name, 'Existing project')
        self.assertEqual(CostEstimate.objects.get(pk=estimate.pk).result, {'total': 10})

    def test_database_connection_failure_is_clear(self):
        with patch.object(connections['default'], 'ensure_connection', side_effect=OSError('database unavailable')):
            with self.assertRaisesRegex(CommandError, 'Could not verify the configured database'):
                call_command('seed_initial_data', noinput=True, stdout=StringIO())

    def test_build_runs_seed_only_after_migrations(self):
        with open('build.sh', encoding='utf-8') as build_script:
            commands = [line.strip() for line in build_script if line.strip().startswith('python manage.py')]
        self.assertLess(commands.index('python manage.py migrate --noinput'),
                        commands.index('python manage.py seed_initial_data --noinput'))

