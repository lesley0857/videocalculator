import importlib

from django.apps import apps
from django.db import connection
from django.test import TransactionTestCase

from apps.pricing.models import ProductionTool
from apps.video_registry.models import Provider


repair_offering_column = importlib.import_module(
    'apps.pricing.migrations.0009_repair_productiontool_offering_column'
).ensure_productiontool_offering_column


class ProductionToolOfferingColumnRepairTests(TransactionTestCase):
    def test_missing_nullable_offering_column_is_added_without_losing_rows(self):
        provider = Provider.objects.create(
            name='Schema Repair Provider',
            slug='schema-repair-provider',
        )
        tool = ProductionTool.objects.create(
            provider=provider,
            name='Schema Repair Tool',
            slug='schema-repair-tool',
            kind=ProductionTool.Kind.SUBSCRIPTION,
            activities=['script'],
        )

        with connection.schema_editor() as schema_editor:
            schema_editor.remove_field(
                ProductionTool,
                ProductionTool._meta.get_field('offering'),
            )
            repair_offering_column(apps, schema_editor)

        tool.refresh_from_db()
        self.assertEqual(tool.provider_id, provider.pk)
        self.assertEqual(tool.name, 'Schema Repair Tool')
        self.assertIsNone(tool.offering_id)

        with connection.cursor() as cursor:
            columns = {
                column.name
                for column in connection.introspection.get_table_description(
                    cursor, ProductionTool._meta.db_table
                )
            }
        self.assertIn('offering_id', columns)
