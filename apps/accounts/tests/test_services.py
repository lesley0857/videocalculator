from django.contrib.auth import get_user_model
from django.test import TestCase
from apps.accounts.services import register_user, deactivate_user

User = get_user_model()


class AccountServicesTests(TestCase):
    def test_register_user_service(self):
        user = register_user(
            email="service_test@example.com",
            password="ServicePassword123!",
            first_name="Alice",
            last_name="Smith",
        )
        self.assertEqual(user.email, "service_test@example.com")
        self.assertEqual(user.first_name, "Alice")
        self.assertTrue(user.check_password("ServicePassword123!"))

    def test_deactivate_user_service(self):
        user = register_user(email="deactivate_test@example.com", password="password123")
        self.assertTrue(user.is_active)
        deactivated = deactivate_user(user)
        self.assertFalse(deactivated.is_active)

