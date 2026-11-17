from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.utils.http import url_has_allowed_host_and_scheme
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views import View

from apps.accounts.forms import EmailAuthenticationForm, RegistrationForm


class ProfilePlaceholderView(View):
    """
    Placeholder view for account profile.
    Delegates any operations to account services.
    """
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'authenticated': False}, status=401)
        return JsonResponse({
            'authenticated': True,
            'email': request.user.email,
            'full_name': request.user.get_full_name(),
        })


class AccountLoginView(LoginView):
    authentication_form = EmailAuthenticationForm
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True


class AccountLogoutView(LogoutView):
    next_page = 'home'


def register_view(request):
    if request.user.is_authenticated:
        return redirect('workspace:dashboard')
    form = RegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        next_url = request.POST.get('next') or request.GET.get('next', '')
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
            return redirect(next_url)
        return redirect('workspace:dashboard')
    return render(request, 'accounts/register.html', {'form': form})

