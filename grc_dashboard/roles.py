"""
Role definitions for ICARIS.

Access is enforced with Django's model permissions. Every authenticated user
can read; changing records requires a permission granted through one of the
groups below. Superusers implicitly hold every permission.

Groups are created (and their permissions re-synced) after every migrate, so
a fresh install and an upgraded one end up with the same roles.
"""
from django.contrib.auth.models import Group, Permission

APP_LABEL = "grc_dashboard"

# Group name -> list of permission codenames within this app.
ROLE_PERMISSIONS: dict[str, list[str]] = {
    # Owns the authorization package: POA&Ms, ConMon requirements, evidence.
    "ISSO": [
        "add_issue", "change_issue", "delete_issue",
        "add_risk", "change_risk", "delete_risk",
        "add_artifact", "change_artifact", "delete_artifact",
    ],
    # Day-to-day contributors: may upload evidence and update POA&M progress,
    # but may not create or delete POA&Ms or ConMon requirements.
    "Analyst": [
        "change_issue",
        "change_risk",
        "add_artifact",
    ],
    # Read-only reviewers (assessors, authorizing official staff).
    "Auditor": [],
}


def sync_roles(**kwargs) -> None:
    """Create the role groups and set their permissions. Idempotent."""
    for group_name, codenames in ROLE_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=group_name)
        perms = Permission.objects.filter(
            content_type__app_label=APP_LABEL, codename__in=codenames
        )
        group.permissions.set(perms)
