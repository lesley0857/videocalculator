from django.urls import path
from .views import NotificationsListView

app_name = 'notifications'

urlpatterns = [
    path('', NotificationsListView.as_view(), name='list'),
]

