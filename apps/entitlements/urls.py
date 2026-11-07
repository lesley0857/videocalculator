from django.urls import path
from .views import EntitlementsListView

app_name = 'entitlements'

urlpatterns = [
    path('', EntitlementsListView.as_view(), name='list'),
]

