import json
import re
from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse

from grc_dashboard.models import Issue, Risk

from .factories import make_department, make_issue, make_risk, make_user


class EveryPageRendersTests(TestCase):
    """Regression test: five pages used to crash with TemplateDoesNotExist."""

    def setUp(self):
        self.issue = make_issue()
        self.risk = make_risk()
        self.client.force_login(make_user("admin", is_superuser=True, is_staff=True))

    def test_all_pages_return_200(self):
        urls = [
            reverse("dashboard"),
            reverse("risk_register"),
            reverse("risk_create"),
            reverse("risk_update", args=[self.risk.pk]),
            reverse("risk_delete", args=[self.risk.pk]),
            reverse("issue_tracking"),
            reverse("issue_create"),
            reverse("issue_update", args=[self.issue.pk]),
            reverse("issue_delete", args=[self.issue.pk]),
            reverse("artifacts"),
            reverse("artifact_create"),
            reverse("compliance_tracking"),
            reverse("audit_management"),
            reverse("risk_heatmap_data"),
            reverse("user_guide"),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_poam_page_has_no_dead_links(self):
        response = self.client.get(reverse("issue_tracking"))
        self.assertNotContains(response, 'href="#"')
        self.assertContains(response, reverse("issue_create"))
        self.assertContains(response, reverse("issue_update", args=[self.issue.pk]))


class PoamWorkflowTests(TestCase):
    def setUp(self):
        self.dept = make_department()
        self.isso = make_user("isso", role="ISSO")
        self.client.force_login(self.isso)

    def test_create_poam_defaults_assignee_to_creator(self):
        response = self.client.post(reverse("issue_create"), {
            "title": "Enable FIPS mode on web tier",
            "description": "SC-13 finding",
            "priority": "high",
            "status": "open",
            "source": "assessment",
            "department": self.dept.pk,
            "due_date": "2026-12-01",
        })
        self.assertRedirects(response, reverse("issue_tracking"))
        issue = Issue.objects.get()
        self.assertEqual(issue.assigned_to, self.isso)

    def test_stats_count_overdue_and_resolved(self):
        past = date.today() - timedelta(days=5)
        make_issue(title="overdue", due_date=past, status="open")
        make_issue(title="done", status="closed")
        make_issue(title="future", due_date=date.today() + timedelta(days=30))
        stats = self.client.get(reverse("issue_tracking")).context["stats"]
        self.assertEqual(stats, {"total": 3, "open": 2, "resolved": 1, "overdue": 1})

    def test_department_filter(self):
        other = make_department("Finance")
        make_issue(title="sec item")
        make_issue(title="fin item", department=other)
        response = self.client.get(reverse("issue_tracking"), {"department": other.pk})
        self.assertEqual([i.title for i in response.context["issues"]], ["fin item"])


class ConMonRegisterTests(TestCase):
    def setUp(self):
        self.client.force_login(make_user("isso", role="ISSO"))
        make_risk(title="A", compliance_percentage=100, likelihood=5, impact=5)
        make_risk(title="B", compliance_percentage=60, likelihood=2, impact=3)
        make_risk(title="C", compliance_percentage=10, likelihood=2, impact=3)

    def test_stat_cards_are_populated(self):
        ctx = self.client.get(reverse("risk_register")).context
        self.assertEqual(ctx["total_risks"], 3)
        self.assertEqual(ctx["compliant_count"], 1)
        self.assertEqual(ctx["noncompliant_count"], 2)
        self.assertEqual(ctx["avg_compliance"], 57)

    def test_compliance_status_filter(self):
        ctx = self.client.get(reverse("risk_register"), {"status": "Non-Compliant"}).context
        self.assertEqual(sorted(r.title for r in ctx["risks"]), ["B", "C"])

    def test_compliance_level_filter(self):
        ctx = self.client.get(reverse("risk_register"), {"compliance": "medium"}).context
        self.assertEqual([r.title for r in ctx["risks"]], ["B"])

    def test_heatmap_data_is_safely_embedded(self):
        make_risk(title="</script><script>alert(1)</script>")
        response = self.client.get(reverse("risk_register"))
        self.assertNotContains(response, "</script><script>alert(1)")
        self.assertContains(response, 'id="heatmap-data"')
        match = re.search(rb'<script id="heatmap-data" type="application/json">(.*?)</script>', response.content, re.S)
        cells = json.loads(match.group(1))
        self.assertIn({"likelihood": 5, "impact": 5}, cells)

    def test_edit_saves_owner_and_compliance(self):
        risk = Risk.objects.get(title="C")
        owner = make_user("owner")
        response = self.client.post(reverse("risk_update", args=[risk.pk]), {
            "title": "C", "description": "d", "department": risk.department.pk,
            "owner": owner.pk, "severity": "low", "likelihood": 1, "impact": 1,
            "status": "in_progress", "compliance_percentage": 85,
            "mitigation_plan": "", "identified_date": "2026-10-01", "target_closure_date": "",
        })
        self.assertRedirects(response, reverse("risk_register"))
        risk.refresh_from_db()
        self.assertEqual((risk.owner, risk.compliance_percentage), (owner, 85))
