from django.urls import path
from .views import AccountLoginView, AccountLogoutView, ProfilePlaceholderView, register_view

app_name = 'accounts'

urlpatterns = [
    path('register/', register_view, name='register'),
    path('login/', AccountLoginView.as_view(), name='login'),
    path('logout/', AccountLogoutView.as_view(), name='logout'),
    path('profile/', ProfilePlaceholderView.as_view(), name='profile'),
]

