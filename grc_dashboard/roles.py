"""
Role definitions for ICARIS.

Access is enforced with Django's model permissions. Every authenticated user
can read; changing records requires a permission granted through one of the
groups below. Superusers implicitly hold every permission.

Groups are created (and their permissions re-synced) after every migrate, so
a fresh install and an upgraded one end up with the same roles.
"""
from django.contrib.auth.models import Group, Permission
from django.db.models import Q


def _crud(app: str, *models: str) -> list[str]:
    return [f"{app}.{action}_{model}" for model in models for action in ("add", "change", "delete")]


# Group name -> list of "app_label.codename" permissions.
ROLE_PERMISSIONS: dict[str, list[str]] = {
    # Owns the authorization package: systems, control implementations,
    # packages, POA&Ms, ConMon requirements and evidence.
    "ISSO": [
        *_crud("grc_dashboard", "issue", "risk", "artifact"),
        *_crud("ato", "informationsystem", "controlimplementation", "authorizationpackage", "packagedocument"),
    ],
    # Day-to-day contributors: update control implementations, POA&M progress
    # and ConMon requirements, and upload evidence. Cannot create or delete
    # systems, packages, POA&Ms or requirements.
    "Analyst": [
        "grc_dashboard.change_issue",
        "grc_dashboard.change_risk",
        "grc_dashboard.add_artifact",
        "ato.change_controlimplementation",
        "ato.change_packagedocument",
    ],
    # Read-only reviewers (assessors, authorizing official staff).
    "Auditor": [],
}


def _permission_filter(perms: list[str]) -> Q:
    query = Q(pk__in=[])
    for perm in perms:
        app_label, codename = perm.split(".", 1)
        query |= Q(content_type__app_label=app_label, codename=codename)
    return query


def sync_roles(**kwargs) -> None:
    """Create the role groups and set their permissions. Idempotent."""
    for group_name, perms in ROLE_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=group_name)
        group.permissions.set(Permission.objects.filter(_permission_filter(perms)))
