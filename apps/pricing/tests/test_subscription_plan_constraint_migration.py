import importlib

from django.db import migrations, models
from django.test import SimpleTestCase

from apps.pricing.models import SubscriptionPlan


class SubscriptionPlanConstraintMigrationTests(SimpleTestCase):
    def test_partial_unique_plan_rule_is_a_constraint_not_an_index(self):
        migration_module = importlib.import_module(
            'apps.pricing.migrations.0007_modelpricing_access_route_productiontool_offering_and_more'
        )
        migration = migration_module.Migration
        operations = [
            operation for operation in migration.operations
            if getattr(operation, 'model_name', None) == 'subscriptionplan'
        ]

        unique_operation = next(
            operation for operation in operations
            if getattr(getattr(operation, 'constraint', None), 'name', None) == 'uniq_offering_plan_slug'
        )
        self.assertIsInstance(unique_operation, migrations.AddConstraint)
        self.assertFalse(any(
            isinstance(operation, migrations.AddIndex)
            and isinstance(getattr(operation, 'index', None), models.UniqueConstraint)
            for operation in operations
        ))
        self.assertIn('uniq_offering_plan_slug', {
            constraint.name for constraint in SubscriptionPlan._meta.constraints
        })
        self.assertFalse(any(
            isinstance(index, models.UniqueConstraint)
            for index in SubscriptionPlan._meta.indexes
        ))
