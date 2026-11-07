from django.urls import path
from .views import DevicesListView

app_name = 'devices'

urlpatterns = [
    path('', DevicesListView.as_view(), name='list'),
]

