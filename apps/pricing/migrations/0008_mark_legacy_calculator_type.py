from django.db import migrations


def mark_legacy_estimates_general(apps, schema_editor):
    Estimate = apps.get_model('pricing', 'CostEstimate')
    Estimate.objects.filter(calculator_type__isnull=True).update(calculator_type='general')


class Migration(migrations.Migration):

    dependencies = [('pricing', '0007_modelpricing_access_route_productiontool_offering_and_more')]

    operations = [migrations.RunPython(mark_legacy_estimates_general, migrations.RunPython.noop)]
