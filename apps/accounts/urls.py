from django.urls import path
from .views import ProfilePlaceholderView

app_name = 'accounts'

urlpatterns = [
    path('profile/', ProfilePlaceholderView.as_view(), name='profile'),
]

