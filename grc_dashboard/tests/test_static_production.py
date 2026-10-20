"""
Render pages with the production static-files backend.

The regular test settings use plain StaticFilesStorage. In production,
WhiteNoise's manifest storage raises an error for any {% static %} path
that was not collected, which turns a missing file into a 500 on every
page. A missing favicon once did exactly that, so this test collects static
files for real and renders the pages through the manifest backend.
"""
import io
import shutil
import tempfile

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from .factories import make_user

MANIFEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}


class ManifestStaticTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.static_root = tempfile.mkdtemp()
        cls.override = override_settings(STORAGES=MANIFEST_STORAGES, STATIC_ROOT=cls.static_root)
        cls.override.enable()
        call_command("collectstatic", interactive=False, verbosity=0, stdout=io.StringIO())

    @classmethod
    def tearDownClass(cls):
        cls.override.disable()
        shutil.rmtree(cls.static_root, ignore_errors=True)
        super().tearDownClass()

    def test_login_page_renders(self):
        self.assertEqual(self.client.get(reverse("login")).status_code, 200)

    def test_app_pages_render_with_hashed_assets(self):
        self.client.force_login(make_user("admin", is_superuser=True, is_staff=True))
        for name in ["dashboard", "issue_tracking", "risk_register", "artifacts", "ato:system_list", "ato:control_list"]:
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
        # Assets come from the app itself with content hashes, never a CDN.
        self.assertRegex(response.content.decode(), r"/static/vendor/fontawesome/css/all\.min\.[0-9a-f]{12}\.css")
        self.assertNotIn("cdnjs.cloudflare.com", response.content.decode())
