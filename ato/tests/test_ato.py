import io
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ato import services
from ato.models import (
    AuthorizationPackage,
    ControlImplementation,
    InformationSystem,
    PackageDocument,
    SecurityControl,
    systems_expiring,
)
from grc_dashboard.tests.factories import make_issue, make_user

TODAY = timezone.localdate()


def make_system(**kwargs) -> InformationSystem:
    defaults = {"name": "Mission Data Platform", "acronym": "MDP"}
    defaults.update(kwargs)
    return InformationSystem.objects.create(**defaults)


class CatalogMixin:
    @classmethod
    def setUpTestData(cls):
        call_command("import_oscal_catalog", stdout=io.StringIO())


class CategorizationTests(TestCase):
    def test_high_water_mark(self):
        system = make_system(confidentiality="low", integrity="high", availability="moderate")
        self.assertEqual(system.categorization, "high")
        self.assertEqual(system.get_categorization_display(), "High")

    def test_all_low_is_low(self):
        system = make_system(confidentiality="low", integrity="low", availability="low")
        self.assertEqual(system.categorization, "low")


class BaselineTests(CatalogMixin, TestCase):
    def test_apply_moderate_baseline(self):
        system = make_system()
        self.assertEqual(services.apply_baseline(system), 287)
        self.assertEqual(system.implementations.count(), 287)

    def test_apply_is_idempotent_and_keeps_tailoring(self):
        system = make_system(confidentiality="low", integrity="low", availability="low")
        services.apply_baseline(system)
        impl = system.implementations.get(control__control_id="ac-2")
        impl.status = ControlImplementation.Status.IMPLEMENTED
        impl.save()
        self.assertEqual(services.apply_baseline(system), 0)
        impl.refresh_from_db()
        self.assertEqual(impl.status, "implemented")

    def test_raising_categorization_adds_only_the_difference(self):
        system = make_system(confidentiality="low", integrity="low", availability="low")
        services.apply_baseline(system)
        system.confidentiality = "moderate"
        system.save()
        self.assertEqual(services.apply_baseline(system), 287 - 149)

    def test_summary_excludes_not_applicable(self):
        system = make_system(confidentiality="low", integrity="low", availability="low")
        services.apply_baseline(system)
        impls = list(system.implementations.all()[:4])
        impls[0].status = impls[1].status = "implemented"
        impls[2].status = "not_applicable"
        impls[2].implementation_statement = "No wireless"
        for i in impls[:3]:
            i.save()
        summary = system.implementation_summary()
        self.assertEqual(summary["implemented"], 2)
        self.assertEqual(summary["percent_implemented"], round(100 * 2 / 148))


class ImplementationValidationTests(CatalogMixin, TestCase):
    def setUp(self):
        self.impl = ControlImplementation(system=make_system(), control=SecurityControl.objects.get(control_id="ac-2"))

    def test_not_applicable_requires_justification(self):
        self.impl.status = "not_applicable"
        with self.assertRaises(ValidationError):
            self.impl.full_clean()

    def test_inherited_requires_provider(self):
        self.impl.origination = "inherited"
        with self.assertRaises(ValidationError):
            self.impl.full_clean()
        self.impl.inherited_from = "Enterprise IAM (common control provider)"
        self.impl.full_clean()


class PackageTests(TestCase):
    def setUp(self):
        self.system = make_system()

    def test_new_package_gets_standard_checklist(self):
        package = services.create_package(self.system, "FY27 authorization")
        types = set(package.documents.values_list("doc_type", flat=True))
        self.assertEqual(types, set(PackageDocument.DEFAULT_REQUIRED))
        self.assertEqual(package.readiness(), {"required": 9, "complete": 0, "percent": 0})

    def test_readiness_counts_final_and_approved(self):
        package = services.create_package(self.system, "FY27 authorization")
        package.documents.filter(doc_type__in=["ssp", "sar"]).update(status="final")
        package.documents.filter(doc_type="poam").update(status="approved")
        package.documents.filter(doc_type="cp").update(status="draft")
        self.assertEqual(package.readiness()["complete"], 3)

    def test_decided_package_needs_decision_and_date(self):
        package = AuthorizationPackage(system=self.system, name="x", status="decided")
        with self.assertRaises(ValidationError) as ctx:
            package.full_clean()
        self.assertIn("decision", ctx.exception.message_dict)
        self.assertIn("decision_date", ctx.exception.message_dict)

    def test_ato_needs_termination_date_or_ongoing(self):
        package = AuthorizationPackage(system=self.system, name="x", status="decided", decision="ato", decision_date=TODAY)
        with self.assertRaises(ValidationError):
            package.full_clean()
        package.ongoing_authorization = True
        package.full_clean()

    def test_conditional_ato_needs_conditions(self):
        package = AuthorizationPackage(
            system=self.system, name="x", status="decided", decision="ato_conditions",
            decision_date=TODAY, expiration_date=TODAY + timedelta(days=90),
        )
        with self.assertRaises(ValidationError) as ctx:
            package.full_clean()
        self.assertIn("conditions", ctx.exception.message_dict)

    def test_expiry_states(self):
        package = AuthorizationPackage(system=self.system, name="x", decision="ato", decision_date=TODAY)
        for days, state in [(400, "ok"), (150, "warning"), (30, "critical"), (-1, "expired")]:
            package.expiration_date = TODAY + timedelta(days=days)
            self.assertEqual(package.expiry_state, state, days)
        self.assertFalse(package.is_authorized)  # expired yesterday

    def test_dato_is_never_authorized(self):
        package = AuthorizationPackage(system=self.system, name="x", decision="dato", decision_date=TODAY)
        self.assertFalse(package.is_authorized)

    def test_expiring_report_ignores_superseded_packages(self):
        AuthorizationPackage.objects.create(
            system=self.system, name="2023", status="decided", decision="ato",
            decision_date=TODAY - timedelta(days=1000), expiration_date=TODAY + timedelta(days=20),
        )
        self.assertEqual(len(systems_expiring()), 1)
        AuthorizationPackage.objects.create(
            system=self.system, name="2026 renewal", status="decided", decision="ato",
            decision_date=TODAY - timedelta(days=5), expiration_date=TODAY + timedelta(days=1090),
        )
        self.assertEqual(systems_expiring(), [])


class AtoViewTests(CatalogMixin, TestCase):
    def setUp(self):
        self.system = make_system()
        services.apply_baseline(self.system)
        self.package = services.create_package(self.system, "FY27 authorization")
        self.impl = self.system.implementations.get(control__control_id="ac-2")

    def test_pages_render_for_auditor(self):
        self.client.force_login(make_user("auditor", role="Auditor"))
        urls = [
            reverse("ato:system_list"),
            reverse("ato:system_detail", args=[self.system.pk]),
            reverse("ato:system_detail", args=[self.system.pk]) + "?family=AC&status=not_started&q=account",
            reverse("ato:package_detail", args=[self.package.pk]),
            reverse("ato:control_list") + "?baseline=moderate&q=account",
            reverse("ato:control_detail", args=["ac-2"]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_auditor_cannot_change_anything(self):
        self.client.force_login(make_user("auditor", role="Auditor"))
        self.assertEqual(self.client.get(reverse("ato:system_create")).status_code, 403)
        self.assertEqual(self.client.get(reverse("ato:implementation_update", args=[self.impl.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("ato:system_apply_baseline", args=[self.system.pk])).status_code, 403)

    def test_analyst_updates_implementation_but_cannot_register_systems(self):
        self.client.force_login(make_user("analyst", role="Analyst"))
        self.assertEqual(self.client.get(reverse("ato:system_create")).status_code, 403)
        response = self.client.post(reverse("ato:implementation_update", args=[self.impl.pk]), {
            "status": "implemented", "origination": "hybrid", "inherited_from": "",
            "responsible_role": "IAM team", "implementation_statement": "Accounts managed in Entra ID.",
            "assessment_result": "satisfied", "last_assessed": str(TODAY),
        })
        self.assertEqual(response.status_code, 302)
        self.impl.refresh_from_db()
        self.assertEqual((self.impl.status, self.impl.assessment_result), ("implemented", "satisfied"))

    def test_invalid_implementation_shows_errors(self):
        self.client.force_login(make_user("analyst", role="Analyst"))
        response = self.client.post(reverse("ato:implementation_update", args=[self.impl.pk]), {
            "status": "not_applicable", "origination": "system", "assessment_result": "not_assessed",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Explain why the control is not applicable")

    def test_isso_registers_system_and_applies_baseline(self):
        self.client.force_login(make_user("isso", role="ISSO"))
        response = self.client.post(reverse("ato:system_create"), {
            "name": "HR Portal", "acronym": "HRP", "description": "", "environment": "cloud",
            "confidentiality": "low", "integrity": "low", "availability": "low", "rmf_step": "categorize",
            "authorizing_official": "",
        })
        system = InformationSystem.objects.get(acronym="HRP")
        self.assertRedirects(response, system.get_absolute_url())
        self.assertEqual(self.client.get(reverse("ato:system_apply_baseline", args=[system.pk])).status_code, 405)
        self.client.post(reverse("ato:system_apply_baseline", args=[system.pk]))
        self.assertEqual(system.implementations.count(), 149)

    def test_isso_records_ato_decision(self):
        self.client.force_login(make_user("isso", role="ISSO"))
        response = self.client.post(reverse("ato:package_update", args=[self.package.pk]), {
            "name": self.package.name, "status": "decided", "decision": "ato",
            "decision_date": str(TODAY), "expiration_date": str(TODAY + timedelta(days=1095)),
            "conditions": "",
        })
        self.assertEqual(response.status_code, 302)
        self.system.refresh_from_db()
        self.assertTrue(self.system.current_authorization.is_authorized)

    def test_poam_linked_to_system_shows_on_system_page(self):
        make_issue(title="Disable stale accounts", system=self.system, control=self.impl.control)
        self.client.force_login(make_user("auditor", role="Auditor"))
        response = self.client.get(reverse("ato:system_detail", args=[self.system.pk]))
        self.assertContains(response, "Disable stale accounts")
