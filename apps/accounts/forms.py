from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError

from apps.accounts.models import User
from apps.accounts.services import register_user


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(label='Email', widget=forms.EmailInput(attrs={'autocomplete': 'email'}))


class RegistrationForm(forms.Form):
    email = forms.EmailField(max_length=254)
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    password1 = forms.CharField(label='Password', strip=False, widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirm password', strip=False, widget=forms.PasswordInput)

    def clean_email(self):
        email = User.objects.normalize_email(self.cleaned_data['email'])
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError('An account with this email already exists.')
        return email

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get('password1')
        password2 = cleaned.get('password2')
        if password1 and password2 and password1 != password2:
            self.add_error('password2', 'The passwords do not match.')
        if password1:
            try:
                password_validation.validate_password(password1)
            except ValidationError as exc:
                self.add_error('password1', exc)
        return cleaned

    def save(self):
        return register_user(
            email=self.cleaned_data['email'], password=self.cleaned_data['password1'],
            first_name=self.cleaned_data['first_name'], last_name=self.cleaned_data['last_name'],
        )
