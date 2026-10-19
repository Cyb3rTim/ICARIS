from django.apps import AppConfig
from django.db.models.signals import post_migrate


class GrcDashboardConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "grc_dashboard"
    verbose_name = "ICARIS GRC"

    def ready(self):
        from .roles import sync_roles

        # Run after every app's migrate signal (not just this app's) so that
        # permissions belonging to apps listed later, such as ato, exist first.
        post_migrate.connect(sync_roles, dispatch_uid="icaris_sync_roles")
