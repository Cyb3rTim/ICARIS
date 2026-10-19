from django.test import TestCase
from django.urls import reverse

from .factories import PASSWORD, make_user


class LogoutTests(TestCase):
    def setUp(self):
        self.user = make_user("isso", role="ISSO")
        self.client.force_login(self.user)

    def test_get_logout_is_refused(self):
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_post_logout_ends_session(self):
        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, reverse("login"))
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)


class LoginTests(TestCase):
    def test_login_page_renders(self):
        self.assertEqual(self.client.get(reverse("login")).status_code, 200)

    def test_valid_login_reaches_dashboard(self):
        make_user("analyst", role="Analyst")
        response = self.client.post(reverse("login"), {"username": "analyst", "password": PASSWORD})
        self.assertRedirects(response, reverse("dashboard"))

    def test_bad_password_is_rejected(self):
        make_user("analyst", role="Analyst")
        response = self.client.post(reverse("login"), {"username": "analyst", "password": "wrong"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
