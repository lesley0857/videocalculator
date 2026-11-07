from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.urls import reverse


class ProjectSetupTests(SimpleTestCase):
    def test_custom_user_model_configured(self):
        self.assertEqual(settings.AUTH_USER_MODEL, 'accounts.User')

    def test_all_initial_apps_installed(self):
        expected_apps = [
            'apps.accounts',
            'apps.products',
            'apps.orders',
            'apps.payments',
            'apps.entitlements',
            'apps.devices',
            'apps.calculators',
            'apps.notifications',
            'apps.analytics',
        ]
        for app in expected_apps:
            self.assertIn(app, settings.INSTALLED_APPS)


class HomeViewTests(TestCase):
    def test_home_page_renders_successfully(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Commercial Calculator Platform")
        self.assertContains(response, "Talking Flyer Calculator")
        self.assertContains(response, "AI Video Generation Calculator")

