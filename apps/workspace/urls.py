from django.urls import path

from apps.workspace.views import (
    EstimateCompareApiView, EstimateDetailApiView, ProjectArchiveApiView,
    ProjectCollectionApiView, ProjectDetailApiView, ProjectEstimatesApiView,
    dashboard_view, estimate_compare_view, estimate_detail_view, project_archive_view,
    project_create_view, project_detail_view, project_edit_view, project_estimate_create_view,
    project_list_view, project_restore_view,
)

app_name = 'workspace'
urlpatterns = [
    path('', dashboard_view, name='dashboard'),
    path('projects/', project_list_view, name='project-list'),
    path('projects/new/', project_create_view, name='project-create'),
    path('projects/<uuid:project_id>/', project_detail_view, name='project-detail'),
    path('projects/<uuid:project_id>/edit/', project_edit_view, name='project-edit'),
    path('projects/<uuid:project_id>/archive/', project_archive_view, name='project-archive'),
    path('projects/<uuid:project_id>/restore/', project_restore_view, name='project-restore'),
    path('projects/<uuid:project_id>/estimates/new/', project_estimate_create_view, name='estimate-create'),
    path('estimates/<uuid:estimate_id>/', estimate_detail_view, name='estimate-detail'),
    path('estimates/compare/', estimate_compare_view, name='estimate-compare'),
    path('api/projects/', ProjectCollectionApiView.as_view(), name='api-project-list'),
    path('api/projects/<uuid:project_id>/', ProjectDetailApiView.as_view(), name='api-project-detail'),
    path('api/projects/<uuid:project_id>/archive/', ProjectArchiveApiView.as_view(), name='api-project-archive'),
    path('api/projects/<uuid:project_id>/estimates/', ProjectEstimatesApiView.as_view(), name='api-project-estimates'),
    path('api/estimates/<uuid:estimate_id>/', EstimateDetailApiView.as_view(), name='api-estimate-detail'),
    path('api/estimates/compare/', EstimateCompareApiView.as_view(), name='api-estimate-compare'),
]
