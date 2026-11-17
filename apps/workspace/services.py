"""Owner-scoped project, estimate-history, and comparison services."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.pricing.models import CostEstimate
from apps.pricing.services import ESTIMATE_INPUT_SEMANTICS, estimate_production_cost
from apps.workspace.models import Project


def project_queryset(owner, *, include_archived=True):
    queryset = Project.objects.filter(owner=owner).annotate(estimate_count=Count('estimates'))
    if not include_archived:
        queryset = queryset.filter(status=Project.Status.ACTIVE)
    return queryset.order_by('-updated_at', '-created_at')


def get_project(owner, project_id):
    try:
        return Project.objects.filter(owner=owner, pk=project_id).first()
    except (ValidationError, ValueError, TypeError):
        return None


def create_project(owner, *, name, description=''):
    return Project.objects.create(owner=owner, name=name, description=description)


def update_project(project, *, name, description=''):
    project.name = name
    project.description = description
    project.save(update_fields=('name', 'description', 'updated_at'))
    return project


def set_project_archived(project, archived):
    if archived:
        project.archive()
    else:
        project.restore()
    return project


@transaction.atomic
def calculate_and_save_estimate(owner, project, inputs):
    """Use Task 006 pricing calculation and attach the immutable snapshot."""
    if project.owner_id != owner.pk:
        raise ValidationError('Project not found.')
    if project.status != Project.Status.ACTIVE:
        raise ValidationError('Restore this project before saving a new estimate.')
    result, estimate = estimate_production_cost(inputs, owner=owner, project=project)
    return result, estimate


def estimate_queryset(owner, project=None):
    queryset = CostEstimate.objects.filter(owner=owner, project__owner=owner).select_related('project')
    if project is not None:
        queryset = queryset.filter(project=project)
    return queryset.order_by('-created_at')


def get_estimate(owner, estimate_id):
    return estimate_queryset(owner).filter(pk=estimate_id).first()


def compare_estimates(owner, estimate_ids):
    if not isinstance(estimate_ids, list) or not 2 <= len(estimate_ids) <= 10:
        raise ValidationError('Select between two and ten estimates to compare.')
    if len(set(map(str, estimate_ids))) != len(estimate_ids):
        raise ValidationError('Duplicate estimate references are not allowed.')
    found = list(estimate_queryset(owner).filter(pk__in=estimate_ids))
    if len(found) != len(estimate_ids):
        raise LookupError('One or more estimates were not found.')
    found_by_id = {str(item.pk): item for item in found}
    ordered = [found_by_id[str(item_id)] for item_id in estimate_ids]
    return [estimate_comparison_snapshot(item) for item in ordered]


def estimate_comparison_snapshot(estimate):
    result = estimate.result
    commercial = result.get('commercial', {})
    components = estimate.inputs.get('components', [])
    models = []
    for line in result.get('model_costs', []):
        model = line.get('model') or {}
        models.append({
            'provider': model.get('provider'), 'name': model.get('name'), 'version': model.get('version'),
            'workflow': (line.get('workflow') or {}).get('slug'), 'pricing_method': line.get('pricing_method'),
        })
    return {
        'id': str(estimate.pk), 'project_id': str(estimate.project_id), 'project_name': estimate.project.name,
        'created_at': estimate.created_at.isoformat(), 'calculator_type': estimate.calculator_type,
        'status': result.get('status', 'unknown'),
        'currency': commercial.get('currency') or result.get('output_currency'),
        'production_cost': commercial.get('total_estimated_production_cost'),
        'known_partial_cost': commercial.get('known_partial_cost'),
        'suggested_selling_price': commercial.get('suggested_selling_price'),
        'gross_profit': commercial.get('gross_profit'),
        'gross_margin_percentage': commercial.get('gross_margin_percentage'),
        'models': models,
        'plans': sorted({line.get('subscription_plan') for line in result.get('model_costs', []) if line.get('subscription_plan')}),
        'components': components,
        'operations': estimate.inputs.get('operations', []),
        'retry_assumptions': [component.get('retry_allowance', 0) for component in components],
        'input_snapshot': estimate.inputs, 'result_snapshot': result,
        'input_semantics': ESTIMATE_INPUT_SEMANTICS,
    }
