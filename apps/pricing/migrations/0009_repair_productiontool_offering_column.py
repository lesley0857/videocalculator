from django.db import migrations


def ensure_productiontool_offering_column(apps, schema_editor):
    ProductionTool = apps.get_model('pricing', 'ProductionTool')
    field = ProductionTool._meta.get_field('offering')
    table_name = ProductionTool._meta.db_table

    with schema_editor.connection.cursor() as cursor:
        columns = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(
                cursor, table_name
            )
        }

    if field.column not in columns:
        # The field is nullable in migration 0007, so adding it preserves every
        # existing ProductionTool row and gives unlinked rows a NULL offering.
        schema_editor.add_field(ProductionTool, field)


class Migration(migrations.Migration):
    dependencies = [
        ('pricing', '0008_mark_legacy_calculator_type'),
    ]

    operations = [
        # Migration state already contains this field from 0007. This operation
        # reconciles only databases where the physical column is missing.
        migrations.RunPython(
            ensure_productiontool_offering_column,
            migrations.RunPython.noop,
        ),
    ]
