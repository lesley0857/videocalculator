import json
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.decorators.http import require_POST

from apps.pricing.services import ESTIMATE_INPUT_SEMANTICS, get_test_interface_data
from apps.workspace.forms import ProjectForm
from apps.workspace.models import Project
from apps.workspace.services import (
    calculate_and_save_estimate, compare_estimates, create_project, estimate_comparison_snapshot,
    estimate_queryset, get_estimate, get_project, project_queryset, set_project_archived, update_project,
)


def _project_or_404(owner, project_id):
    project = get_project(owner, project_id)
    if project is None:
        raise Http404
    return project


def _estimate_or_404(owner, estimate_id):
    estimate = get_estimate(owner, estimate_id)
    if estimate is None:
        raise Http404
    return estimate


@login_required
def dashboard_view(request):
    projects = project_queryset(request.user)
    recent_projects = projects[:5]
    recent_estimates = estimate_queryset(request.user).select_related('project')[:8]
    return render(request, 'workspace/dashboard.html', {
        'total_projects': projects.count(),
        'active_projects': projects.filter(status=Project.Status.ACTIVE).count(),
        'archived_projects': projects.filter(status=Project.Status.ARCHIVED).count(),
        'total_estimates': estimate_queryset(request.user).count(),
        'recent_projects': recent_projects,
        'recent_estimates': recent_estimates,
    })


@login_required
def project_list_view(request):
    include_archived = request.GET.get('status') != Project.Status.ACTIVE
    projects = project_queryset(request.user, include_archived=include_archived)
    if request.GET.get('status') in Project.Status.values:
        projects = projects.filter(status=request.GET['status'])
    page = Paginator(projects, 20).get_page(request.GET.get('page'))
    return render(request, 'workspace/project_list.html', {'page': page, 'status_filter': request.GET.get('status', '')})


@login_required
def project_create_view(request):
    form = ProjectForm(request.POST or None, owner=request.user)
    if request.method == 'POST' and form.is_valid():
        project = create_project(request.user, **form.cleaned_data)
        next_url = request.POST.get('next') or request.GET.get('next', '')
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
            return redirect(next_url)
        return redirect('workspace:project-detail', project_id=project.pk)
    return render(request, 'workspace/project_form.html', {'form': form, 'heading': 'Create project', 'next_url': request.GET.get('next', '')})


@login_required
def project_detail_view(request, project_id):
    project = _project_or_404(request.user, project_id)
    estimates = Paginator(estimate_queryset(request.user, project), 20).get_page(request.GET.get('page'))
    return render(request, 'workspace/project_detail.html', {'project': project, 'estimates': estimates})


@login_required
def project_edit_view(request, project_id):
    project = _project_or_404(request.user, project_id)
    form = ProjectForm(request.POST or None, instance=project, owner=request.user)
    if request.method == 'POST' and form.is_valid():
        update_project(project, **form.cleaned_data)
        return redirect('workspace:project-detail', project_id=project.pk)
    return render(request, 'workspace/project_form.html', {'form': form, 'project': project, 'heading': 'Edit project'})


@login_required
@require_POST
def project_archive_view(request, project_id):
    project = _project_or_404(request.user, project_id)
    set_project_archived(project, True)
    return redirect('workspace:project-detail', project_id=project.pk)


@login_required
@require_POST
def project_restore_view(request, project_id):
    project = _project_or_404(request.user, project_id)
    set_project_archived(project, False)
    return redirect('workspace:project-detail', project_id=project.pk)


@login_required
def project_estimate_create_view(request, project_id):
    project = _project_or_404(request.user, project_id)
    if project.status != Project.Status.ACTIVE:
        return redirect('workspace:project-detail', project_id=project.pk)
    data = get_test_interface_data()
    starting_inputs = None
    source_id = request.GET.get('from')
    if source_id:
        source = _estimate_or_404(request.user, source_id)
        if source.project_id != project.pk:
            raise Http404
        starting_inputs = source.inputs
    return render(request, 'pricing/cost_test.html', {
        **data, 'workspace_project': project, 'workspace_project_id': str(project.pk),
        'starting_inputs': starting_inputs,
    })


@login_required
def estimate_detail_view(request, estimate_id):
    estimate = _estimate_or_404(request.user, estimate_id)
    return render(request, 'workspace/estimate_detail.html', {
        'estimate': estimate, 'project': estimate.project,
        'comparison': estimate_comparison_snapshot(estimate),
    })


@login_required
def estimate_compare_view(request):
    estimates = None
    error = None
    selected_ids = request.POST.getlist('estimate_ids') if request.method == 'POST' else request.GET.getlist('estimate_ids')
    if selected_ids:
        try:
            estimates = compare_estimates(request.user, selected_ids)
        except (ValidationError, LookupError) as exc:
            error = '; '.join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
    return render(request, 'workspace/estimate_compare.html', {
        'estimates': estimates, 'error': error, 'selected_ids': selected_ids,
    })


def _api_auth_error(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'authentication_required'}, status=401)
    return None


def _json_body(request):
    try:
        value = json.loads(request.body.decode('utf-8'), parse_float=Decimal, parse_int=int)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError('Invalid JSON payload.')
    if not isinstance(value, dict):
        raise ValueError('JSON body must be an object.')
    return value


def _serialize_project(project):
    estimate_count = getattr(project, 'estimate_count', None)
    if estimate_count is None:
        estimate_count = project.estimates.count()
    return {
        'id': str(project.pk), 'name': project.name, 'description': project.description,
        'status': project.status, 'archived_at': project.archived_at.isoformat() if project.archived_at else None,
        'created_at': project.created_at.isoformat(), 'updated_at': project.updated_at.isoformat(),
        'estimate_count': estimate_count,
    }


def _serialize_estimate(estimate):
    snapshot = estimate_comparison_snapshot(estimate)
    return {key: snapshot[key] for key in (
        'id', 'project_id', 'project_name', 'created_at', 'status', 'currency', 'production_cost',
        'known_partial_cost', 'suggested_selling_price', 'gross_profit', 'gross_margin_percentage', 'models')}


class ProjectCollectionApiView(View):
    def get(self, request):
        error = _api_auth_error(request)
        if error:
            return error
        queryset = project_queryset(request.user)
        if request.GET.get('status') in Project.Status.values:
            queryset = queryset.filter(status=request.GET['status'])
        try:
            page_size = min(max(int(request.GET.get('page_size', 20)), 1), 100)
        except ValueError:
            return JsonResponse({'error': 'page_size must be an integer.'}, status=400)
        page = Paginator(queryset, page_size).get_page(request.GET.get('page'))
        return JsonResponse({'count': page.paginator.count, 'page': page.number,
                             'results': [_serialize_project(project) for project in page.object_list]})

    def post(self, request):
        error = _api_auth_error(request)
        if error:
            return error
        try:
            body = _json_body(request)
            if set(body) - {'name', 'description'}:
                return JsonResponse({'error': 'Only name and description may be supplied.'}, status=400)
            project = create_project(request.user, name=body.get('name', ''), description=body.get('description', ''))
        except (ValueError, ValidationError) as exc:
            return JsonResponse({'error': str(exc.messages if isinstance(exc, ValidationError) else exc)}, status=400)
        return JsonResponse({'project': _serialize_project(project)}, status=201)


class ProjectDetailApiView(View):
    def get(self, request, project_id):
        error = _api_auth_error(request)
        if error:
            return error
        project = get_project(request.user, project_id)
        if project is None:
            return JsonResponse({'error': 'not_found'}, status=404)
        return JsonResponse({'project': _serialize_project(project)})

    def patch(self, request, project_id):
        error = _api_auth_error(request)
        if error:
            return error
        project = get_project(request.user, project_id)
        if project is None:
            return JsonResponse({'error': 'not_found'}, status=404)
        try:
            body = _json_body(request)
            if set(body) - {'name', 'description'}:
                return JsonResponse({'error': 'Only name and description may be changed.'}, status=400)
            update_project(project, name=body.get('name', project.name), description=body.get('description', project.description))
        except (ValueError, ValidationError) as exc:
            return JsonResponse({'error': str(exc.messages if isinstance(exc, ValidationError) else exc)}, status=400)
        return JsonResponse({'project': _serialize_project(project)})


class ProjectArchiveApiView(View):
    def post(self, request, project_id):
        error = _api_auth_error(request)
        if error:
            return error
        project = get_project(request.user, project_id)
        if project is None:
            return JsonResponse({'error': 'not_found'}, status=404)
        try:
            body = _json_body(request)
            archived = body.get('archived')
            if not isinstance(archived, bool):
                raise ValueError('archived must be a boolean.')
            set_project_archived(project, archived)
        except (ValueError, ValidationError) as exc:
            return JsonResponse({'error': str(exc.messages if isinstance(exc, ValidationError) else exc)}, status=400)
        return JsonResponse({'project': _serialize_project(project)})


class ProjectEstimatesApiView(View):
    def get(self, request, project_id):
        error = _api_auth_error(request)
        if error:
            return error
        project = get_project(request.user, project_id)
        if project is None:
            return JsonResponse({'error': 'not_found'}, status=404)
        page = Paginator(estimate_queryset(request.user, project), 20).get_page(request.GET.get('page'))
        return JsonResponse({'count': page.paginator.count, 'page': page.number,
                             'results': [_serialize_estimate(item) for item in page.object_list]})

    def post(self, request, project_id):
        error = _api_auth_error(request)
        if error:
            return error
        project = get_project(request.user, project_id)
        if project is None:
            return JsonResponse({'error': 'not_found'}, status=404)
        try:
            body = _json_body(request)
            if 'owner_id' in body or 'project_id' in body:
                return JsonResponse({'error': 'Owner and project come from the authenticated route.'}, status=400)
            result, estimate = calculate_and_save_estimate(request.user, project, body)
        except (ValueError, TypeError, KeyError, ValidationError) as exc:
            messages = exc.messages if isinstance(exc, ValidationError) else str(exc)
            return JsonResponse({'error': messages}, status=400)
        return JsonResponse({'estimate_id': str(estimate.pk), 'project_id': str(project.pk),
                             'input_semantics': ESTIMATE_INPUT_SEMANTICS, **result},
                            status=200 if result['status'] == 'complete' else 422)


class EstimateDetailApiView(View):
    def get(self, request, estimate_id):
        error = _api_auth_error(request)
        if error:
            return error
        estimate = get_estimate(request.user, estimate_id)
        if estimate is None:
            return JsonResponse({'error': 'not_found'}, status=404)
        return JsonResponse({'estimate_id': str(estimate.pk), 'project_id': str(estimate.project_id),
                             'created_at': estimate.created_at.isoformat(),
                             'calculator_type': estimate.calculator_type,
                             'input_semantics': ESTIMATE_INPUT_SEMANTICS,
                             'input_snapshot': estimate.inputs, 'result_snapshot': estimate.result})


class EstimateCompareApiView(View):
    def post(self, request):
        error = _api_auth_error(request)
        if error:
            return error
        try:
            body = _json_body(request)
            estimates = compare_estimates(request.user, body.get('estimate_ids'))
        except (ValueError, ValidationError) as exc:
            messages = exc.messages if isinstance(exc, ValidationError) else str(exc)
            return JsonResponse({'error': messages}, status=400)
        except LookupError:
            return JsonResponse({'error': 'not_found'}, status=404)
        return JsonResponse({'estimates': estimates})
