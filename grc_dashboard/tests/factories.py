"""Small helpers to build test data without external factory libraries."""
from datetime import date

from django.contrib.auth.models import Group, User

from grc_dashboard.models import Department, Issue, Risk

PASSWORD = "Test-Passw0rd-ICARIS"


def make_user(username: str, role: str | None = None, **extra) -> User:
    user = User.objects.create_user(username=username, password=PASSWORD, **extra)
    if role:
        user.groups.add(Group.objects.get(name=role))
    return user


def make_department(name: str = "Security") -> Department:
    return Department.objects.get_or_create(name=name)[0]


def make_issue(**kwargs) -> Issue:
    defaults = {
        "title": "Remediate missing MFA on admin portal",
        "description": "IA-2(1) finding from annual assessment",
        "priority": "high",
        "department": make_department(),
        "due_date": date(2026, 12, 31),
    }
    defaults.update(kwargs)
    return Issue.objects.create(**defaults)


def make_risk(**kwargs) -> Risk:
    defaults = {
        "title": "Monthly vulnerability scan review",
        "description": "RA-5 continuous monitoring requirement",
        "department": make_department(),
        "severity": "medium",
        "likelihood": 3,
        "impact": 3,
    }
    defaults.update(kwargs)
    return Risk.objects.create(**defaults)
