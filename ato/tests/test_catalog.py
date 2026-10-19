import io

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from ato import catalog as oscal
from ato.models import ControlFamily, SecurityControl

SAMPLE_CATALOG = {
    "catalog": {
        "metadata": {"title": "Sample catalog", "version": "9.9"},
        "groups": [
            {
                "id": "ac",
                "title": "Access Control",
                "controls": [
                    {
                        "id": "ac-2",
                        "title": "Account Management",
                        "params": [
                            {"id": "ac-02_odp.01", "props": [{"name": "alt-identifier", "value": "ac-2_prm_1"}],
                             "label": "personnel or roles"},
                            {"id": "ac-02_odp.02", "select": {"how-many": "one-or-more",
                                                              "choice": ["disable", "remove"]}},
                        ],
                        "props": [
                            {"name": "label", "value": "AC-02", "class": "zero-padded"},
                            {"name": "label", "value": "AC-2"},
                            {"name": "sort-id", "value": "ac-02"},
                        ],
                        "parts": [
                            {"id": "ac-2_smt", "name": "statement", "parts": [
                                {"id": "ac-2_smt.a", "name": "item", "props": [{"name": "label", "value": "a."}],
                                 "prose": "Require approvals by {{ insert: param, ac-2_prm_1 }};"},
                                {"id": "ac-2_smt.b", "name": "item", "props": [{"name": "label", "value": "b."}],
                                 "prose": "{{ insert: param, ac-02_odp.02 }} accounts when no longer needed."},
                            ]},
                            {"id": "ac-2_gdn", "name": "guidance", "prose": "Guidance is not part of the statement."},
                        ],
                        "controls": [
                            {"id": "ac-2.1", "title": "Automated System Account Management",
                             "props": [{"name": "label", "value": "AC-2(1)"}, {"name": "sort-id", "value": "ac-02.01"}]},
                        ],
                    },
                    {
                        "id": "ac-13",
                        "title": "Supervision and Review",
                        "props": [{"name": "label", "value": "AC-13"}, {"name": "status", "value": "withdrawn"}],
                    },
                ],
            }
        ],
    }
}

SAMPLE_PROFILE = {"profile": {"imports": [{"include-controls": [{"with-ids": ["ac-2", "ac-2.1"]}]}]}}


class ParserTests(SimpleTestCase):
    def setUp(self):
        self.data = oscal.parse_catalog(SAMPLE_CATALOG)
        self.by_id = {c.control_id: c for c in self.data.controls}

    def test_families_and_metadata(self):
        self.assertEqual(self.data.families, {"AC": "Access Control"})
        self.assertEqual(self.data.version, "9.9")

    def test_uses_unpadded_label_and_links_enhancements(self):
        self.assertEqual(self.by_id["ac-2"].label, "AC-2")
        self.assertEqual(self.by_id["ac-2.1"].parent_id, "ac-2")
        self.assertIsNone(self.by_id["ac-2"].parent_id)

    def test_statement_renders_assignments_and_selections(self):
        statement = self.by_id["ac-2"].statement
        self.assertIn("a. Require approvals by [Assignment: organization-defined personnel or roles];", statement)
        self.assertIn("b. [Selection (one or more): disable; remove] accounts", statement)
        self.assertNotIn("Guidance", statement)

    def test_withdrawn_flag(self):
        self.assertTrue(self.by_id["ac-13"].withdrawn)
        self.assertFalse(self.by_id["ac-2"].withdrawn)

    def test_profile_baselines(self):
        oscal.apply_baselines(self.data, {"moderate": oscal.parse_profile_ids(SAMPLE_PROFILE)})
        self.assertEqual(self.by_id["ac-2.1"].baselines, ["moderate"])
        self.assertEqual(self.by_id["ac-13"].baselines, [])

    def test_json_round_trip(self):
        again = oscal.CatalogData.from_json(self.data.to_json())
        self.assertEqual(again.controls, self.data.controls)


class BundledCatalogTests(SimpleTestCase):
    """The bundled data must match the published NIST SP 800-53 Rev 5 / 800-53B figures."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.data = oscal.load_bundled()

    def test_twenty_families(self):
        self.assertEqual(len(self.data.families), 20)

    def test_baseline_sizes_match_sp_800_53b(self):
        counts = {lvl: sum(lvl in c.baselines for c in self.data.controls) for lvl in ("low", "moderate", "high")}
        self.assertEqual(counts, {"low": 149, "moderate": 287, "high": 370})

    def test_baselines_are_nested(self):
        for c in self.data.controls:
            if "low" in c.baselines:
                self.assertIn("moderate", c.baselines, c.control_id)
            if "moderate" in c.baselines:
                self.assertIn("high", c.baselines, c.control_id)


class ImportCommandTests(TestCase):
    def test_import_is_idempotent(self):
        out = io.StringIO()
        call_command("import_oscal_catalog", stdout=out)
        self.assertIn("low=149 moderate=287 high=370", out.getvalue())
        first = SecurityControl.objects.count()
        call_command("import_oscal_catalog", stdout=io.StringIO())
        self.assertEqual(SecurityControl.objects.count(), first)
        self.assertEqual(ControlFamily.objects.count(), 20)
        ac21 = SecurityControl.objects.get(control_id="ac-2.1")
        self.assertEqual(ac21.parent.control_id, "ac-2")
        self.assertEqual(SecurityControl.baseline_queryset("moderate").count(), 287)
