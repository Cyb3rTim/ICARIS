from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from grc_dashboard.models import Issue, Risk
from grc_dashboard.roles import ROLE_PERMISSIONS

from .factories import make_issue, make_risk, make_user


class RoleSetupTests(TestCase):
    def test_role_groups_exist_after_migrate(self):
        names = set(Group.objects.values_list("name", flat=True))
        self.assertTrue(set(ROLE_PERMISSIONS).issubset(names))

    def test_isso_holds_full_poam_permissions(self):
        isso = make_user("isso", role="ISSO")
        self.assertTrue(isso.profile.can_manage_poams())

    def test_analyst_cannot_manage_poams(self):
        analyst = make_user("analyst", role="Analyst")
        self.assertFalse(analyst.profile.can_manage_poams())


class AnonymousAccessTests(TestCase):
    def test_protected_pages_redirect_to_login(self):
        for name in ["dashboard", "risk_register", "issue_tracking", "artifacts"]:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, name)
            self.assertTrue(response["Location"].startswith("/accounts/login/"), name)


class PoamWritePermissionTests(TestCase):
    def setUp(self):
        self.issue = make_issue()

    def test_user_without_role_cannot_delete_poam(self):
        self.client.force_login(make_user("nobody"))
        response = self.client.post(reverse("issue_delete", args=[self.issue.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Issue.objects.filter(pk=self.issue.pk).exists())

    def test_analyst_cannot_delete_poam(self):
        self.client.force_login(make_user("analyst", role="Analyst"))
        response = self.client.post(reverse("issue_delete", args=[self.issue.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Issue.objects.filter(pk=self.issue.pk).exists())

    def test_auditor_cannot_create_poam(self):
        self.client.force_login(make_user("auditor", role="Auditor"))
        response = self.client.get(reverse("issue_create"))
        self.assertEqual(response.status_code, 403)

    def test_isso_can_delete_poam(self):
        self.client.force_login(make_user("isso", role="ISSO"))
        response = self.client.post(reverse("issue_delete", args=[self.issue.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Issue.objects.filter(pk=self.issue.pk).exists())


class ConMonWritePermissionTests(TestCase):
    def setUp(self):
        self.risk = make_risk()

    def test_user_without_role_cannot_delete_requirement(self):
        self.client.force_login(make_user("nobody"))
        response = self.client.post(reverse("risk_delete", args=[self.risk.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Risk.objects.filter(pk=self.risk.pk).exists())

    def test_isso_can_delete_requirement(self):
        self.client.force_login(make_user("isso", role="ISSO"))
        response = self.client.post(reverse("risk_delete", args=[self.risk.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Risk.objects.filter(pk=self.risk.pk).exists())

    def test_edit_buttons_hidden_without_permission(self):
        self.client.force_login(make_user("auditor", role="Auditor"))
        response = self.client.get(reverse("risk_register"))
        self.assertNotContains(response, reverse("risk_delete", args=[self.risk.pk]))


class ArtifactPermissionTests(TestCase):
    def test_auditor_cannot_open_upload_form(self):
        self.client.force_login(make_user("auditor", role="Auditor"))
        self.assertEqual(self.client.get(reverse("artifact_create")).status_code, 403)

    def test_analyst_can_open_upload_form(self):
        self.client.force_login(make_user("analyst", role="Analyst"))
        self.assertEqual(self.client.get(reverse("artifact_create")).status_code, 200)
