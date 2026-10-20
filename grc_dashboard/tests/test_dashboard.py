import csv
import io
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ato.models import InformationSystem
from grc_dashboard.models import Issue

from .factories import make_issue, make_user


class ClosedAtTests(TestCase):
    def test_closing_sets_and_reopening_clears_closed_at(self):
        issue = make_issue()
        self.assertIsNone(issue.closed_at)
        issue.status = "resolved"
        issue.save()
        self.assertIsNotNone(issue.closed_at)
        first_close = issue.closed_at
        issue.status = "closed"
        issue.save()
        self.assertEqual(issue.closed_at, first_close)  # not reset when moving between closed states
        issue.status = "in_progress"
        issue.save()
        self.assertIsNone(issue.closed_at)

    def test_is_overdue(self):
        today = timezone.localdate()
        self.assertTrue(make_issue(due_date=today - timedelta(days=1)).is_overdue)
        self.assertFalse(make_issue(due_date=today + timedelta(days=1)).is_overdue)
        self.assertFalse(make_issue(due_date=today - timedelta(days=1), status="closed").is_overdue)


class DashboardTests(TestCase):
    def setUp(self):
        self.client.force_login(make_user("auditor", role="Auditor"))

    def test_empty_dashboard_renders_without_placeholder_numbers(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        for fake in ("Pending RFIs", "Manage RFIs", "vs. last month", "[4, 3, 6, 2, 5, 3]"):
            self.assertNotIn(fake, content)
        self.assertEqual(response.context["open_poam_count"], 0)
        self.assertEqual(response.context["percent_implemented"], 0)

    def test_metrics_and_charts_use_live_data(self):
        today = timezone.localdate()
        make_issue(priority="critical", due_date=today - timedelta(days=2))
        make_issue(priority="high")
        make_issue(priority="high", status="closed")
        response = self.client.get(reverse("dashboard"))
        ctx = response.context
        self.assertEqual(ctx["open_poam_count"], 2)
        self.assertEqual(ctx["overdue_poam_count"], 1)
        self.assertEqual(ctx["priority"]["counts"], [0, 0, 1, 1])  # closed item excluded
        self.assertEqual(sum(ctx["activity"]["opened"]), 3)
        self.assertEqual(ctx["activity"]["closed"][-1], 1)
        self.assertEqual(len(ctx["activity"]["labels"]), 6)


class PoamExportTests(TestCase):
    def setUp(self):
        self.system = InformationSystem.objects.create(name="Mission Data Platform", acronym="MDP")
        self.client.force_login(make_user("auditor", role="Auditor"))

    def rows(self, response):
        return list(csv.reader(io.StringIO(response.content.decode())))

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("poam_export")).status_code, 302)

    def test_export_contents(self):
        make_issue(title="Enable MFA", system=self.system, priority="high")
        response = self.client.get(reverse("poam_export"))
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("attachment;", response["Content-Disposition"])
        header, row = self.rows(response)
        self.assertEqual(header[0], "POA&M ID")
        record = dict(zip(header, row, strict=True))
        self.assertEqual(record["System"], "MDP")
        self.assertEqual(record["Weakness"], "Enable MFA")
        self.assertEqual(record["Priority"], "High")

    def test_formula_injection_is_neutralized(self):
        make_issue(title='=HYPERLINK("http://evil.example","click")', description="+cmd|' /C calc'!A0")
        _, row = self.rows(self.client.get(reverse("poam_export")))
        self.assertTrue(row[3].startswith("'="))
        self.assertTrue(row[4].startswith("'+"))

    def test_filters_apply(self):
        make_issue(title="open item", status="open")
        make_issue(title="done item", status="closed")
        rows = self.rows(self.client.get(reverse("poam_export"), {"status": "closed"}))
        self.assertEqual([r[3] for r in rows[1:]], ["done item"])


class SeedDemoTests(TestCase):
    def test_refuses_without_debug(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo", stdout=io.StringIO())

    def test_seed_is_repeatable(self):
        out = io.StringIO()
        call_command("seed_demo", "--force", "--password", "Seed-Test-Pass-1", stdout=out)
        counts = (InformationSystem.objects.count(), Issue.objects.count(), User.objects.count())
        call_command("seed_demo", "--force", "--password", "Seed-Test-Pass-1", stdout=io.StringIO())
        self.assertEqual(counts, (InformationSystem.objects.count(), Issue.objects.count(), User.objects.count()))
        self.assertEqual(counts[0], 3)
        self.assertTrue(User.objects.get(username="isso").check_password("Seed-Test-Pass-1"))
        self.assertNotIn("Seed-Test-Pass-1", out.getvalue())  # chosen passwords are never echoed
        # Every page renders with a full demo dataset.
        self.client.force_login(User.objects.get(username="admin"))
        for name in ["dashboard", "issue_tracking", "risk_register", "artifacts", "ato:system_list"]:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertEqual(sum(self.client.get(reverse("dashboard")).context["activity"]["closed"]) > 0, True)
