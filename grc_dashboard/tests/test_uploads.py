import shutil
import tempfile

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from grc_dashboard.models import Artifact
from grc_dashboard.validators import EvidenceFileValidator, validate_evidence_file

from .factories import make_department, make_user

PDF = b"%PDF-1.7\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def upload(name, content, content_type="application/octet-stream"):
    return SimpleUploadedFile(name, content, content_type=content_type)


class ValidatorTests(TestCase):
    def test_accepts_real_pdf(self):
        validate_evidence_file(upload("ssp.pdf", PDF))

    def test_accepts_real_png(self):
        validate_evidence_file(upload("diagram.png", PNG))

    def test_accepts_plain_csv(self):
        validate_evidence_file(upload("scan.csv", b"host,plugin,severity\n10.0.0.5,19506,low\n"))

    def test_rejects_disallowed_extension(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_evidence_file(upload("payload.exe", b"MZ\x90\x00"))
        self.assertEqual(ctx.exception.code, "invalid_extension")

    def test_rejects_executable_renamed_to_pdf(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_evidence_file(upload("evidence.pdf", b"MZ\x90\x00\x03\x00\x00\x00"))
        self.assertEqual(ctx.exception.code, "content_mismatch")

    def test_rejects_html_disguised_as_text(self):
        with self.assertRaises(ValidationError):
            validate_evidence_file(upload("notes.txt", b"<html><script>alert(1)</script></html>"))

    def test_rejects_svg_and_html_extensions(self):
        for name in ("logo.svg", "page.html", "page.htm"):
            with self.assertRaises(ValidationError):
                validate_evidence_file(upload(name, b"<svg onload=alert(1)>"))

    def test_rejects_oversized_file(self):
        small_limit = EvidenceFileValidator(max_bytes=10)
        with self.assertRaises(ValidationError) as ctx:
            small_limit(upload("big.pdf", PDF))
        self.assertEqual(ctx.exception.code, "file_too_large")


class ArtifactUploadFlowTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media)
        self.override.enable()
        self.dept = make_department()
        self.analyst = make_user("analyst", role="Analyst")

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media, ignore_errors=True)

    def post_upload(self, file):
        self.client.force_login(self.analyst)
        return self.client.post(reverse("artifact_create"), {
            "title": "System Security Plan",
            "description": "",
            "category": "ato",
            "department": self.dept.pk,
            "file": file,
        })

    def test_valid_upload_is_stored_under_random_name(self):
        response = self.post_upload(upload("Our SSP v3.pdf", PDF))
        self.assertEqual(response.status_code, 302)
        artifact = Artifact.objects.get()
        self.assertEqual(artifact.original_filename, "Our SSP v3.pdf")
        self.assertNotIn("SSP", artifact.file.name)
        self.assertTrue(artifact.file.name.startswith("artifacts/"))

    def test_spoofed_upload_is_rejected(self):
        response = self.post_upload(upload("ssp.pdf", b"<html>not a pdf</html>"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Artifact.objects.count(), 0)

    def test_download_requires_login_and_forces_attachment(self):
        self.post_upload(upload("Our SSP v3.pdf", PDF))
        artifact = Artifact.objects.get()
        url = reverse("artifact_download", args=[artifact.pk])

        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

        self.client.force_login(make_user("auditor", role="Auditor"))
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("Our SSP v3.pdf", response["Content-Disposition"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(b"".join(response.streaming_content), PDF)

    def test_inline_view_only_for_safe_types(self):
        self.post_upload(upload("Our SSP v3.pdf", PDF))
        artifact = Artifact.objects.get()
        response = self.client.get(reverse("artifact_download", args=[artifact.pk]) + "?inline=1")
        self.assertIn("inline", response["Content-Disposition"])
