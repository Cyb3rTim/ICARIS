from django.apps import AppConfig
from django.db.models.signals import post_migrate


class GrcDashboardConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "grc_dashboard"
    verbose_name = "ICARIS GRC"

    def ready(self):
        from .roles import sync_roles

        post_migrate.connect(sync_roles, sender=self)
