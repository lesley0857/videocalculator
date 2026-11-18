"""Apply the reviewed catalogue after migrations have completed."""

from django.core.management import BaseCommand, call_command
from django.core.management.base import CommandError
from django.db import connections
from django.db.migrations.executor import MigrationExecutor


class Command(BaseCommand):
    help = 'Seed reviewed initial reference data after migrations; existing catalogue rows are preserved.'

    def add_arguments(self, parser):
        parser.add_argument('--noinput', action='store_true', help='Accepted for deployment command compatibility.')

    def handle(self, *args, **options):
        connection = connections['default']
        try:
            connection.ensure_connection()
            executor = MigrationExecutor(connection)
            pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
            if pending:
                names = ', '.join(f'{migration.app_label}.{migration.name}' for migration, _ in pending)
                raise CommandError(f'Database migrations are incomplete; run migrate first. Pending: {names}')

            if connection.vendor == 'postgresql':
                self._check_productiontool_offering_foreign_key(connection)
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(f'Could not verify the configured database and migrations: {exc}') from exc

        self.stdout.write('Database connection, migrations, and production tool schema verified.')
        try:
            call_command('populate_researched_catalogue', apply=True, stdout=self.stdout, stderr=self.stderr)
        except Exception as exc:
            raise CommandError(f'Initial catalogue seeding failed: {exc}') from exc

    @staticmethod
    def _check_productiontool_offering_foreign_key(connection):
        from apps.pricing.models import ProductionTool

        field = ProductionTool._meta.get_field('offering')
        with connection.cursor() as cursor:
            columns = {
                column.name for column in connection.introspection.get_table_description(
                    cursor, ProductionTool._meta.db_table
                )
            }
            if field.column not in columns:
                raise CommandError(
                    'pricing_productiontool.offering_id is missing after migrations; '
                    'migration 0009 must repair the production schema.'
                )
            constraints = connection.introspection.get_constraints(cursor, ProductionTool._meta.db_table)
        column_constraints = [
            details for details in constraints.values()
            if field.column in details.get('columns', [])
        ]
        if not any(details.get('foreign_key') == ('video_registry_provideroffering', 'id') for details in column_constraints):
            raise CommandError(
                'pricing_productiontool.offering_id does not have the expected '
                'foreign key to video_registry_provideroffering(id).'
            )
