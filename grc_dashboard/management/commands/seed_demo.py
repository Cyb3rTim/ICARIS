"""
Populate ICARIS with realistic demo data for screenshots and trial runs.

    python manage.py seed_demo                 # random demo passwords, printed once
    python manage.py seed_demo --password ...  # choose the demo password

Creates demo users for each role, three information systems at different
points in the RMF (one authorized and nearing expiration, one under ongoing
authorization, one under assessment), POA&Ms, ConMon requirements, audits
and evidence artifacts. Safe to re-run: existing demo records are reused.

Never run this against a production database.
"""
import random
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from ato import services as ato_services
from ato.models import AuthorizationPackage, ControlImplementation, InformationSystem, SecurityControl
from grc_dashboard.models import (
    Artifact,
    Audit,
    ComplianceControl,
    ComplianceFramework,
    Department,
    Issue,
    Risk,
)

DEMO_USERS = [
    # username, first, last, role, superuser
    ("admin", "Demo", "Admin", None, True),
    ("isso", "Jordan", "Reyes", "ISSO", False),
    ("analyst", "Sam", "Okafor", "Analyst", False),
    ("auditor", "Priya", "Nair", "Auditor", False),
]

SYSTEMS = [
    {
        "acronym": "MDP", "name": "Mission Data Platform", "environment": "cloud",
        "confidentiality": "moderate", "integrity": "moderate", "availability": "low",
        "rmf_step": "monitor", "authorizing_official": "Deputy CIO",
        "description": "Cloud analytics platform that ingests and correlates mission reporting data.",
        "implemented_share": 0.9,
        "package": {"name": "FY24 authorization", "decision": "ato", "decided_days_ago": 1020, "expires_in": 75},
    },
    {
        "acronym": "HRP", "name": "HR Self-Service Portal", "environment": "cloud",
        "confidentiality": "low", "integrity": "low", "availability": "low",
        "rmf_step": "monitor", "authorizing_official": "Deputy CIO",
        "description": "Employee self-service for leave, benefits and directory updates (SaaS).",
        "implemented_share": 0.97,
        "package": {"name": "Ongoing authorization", "decision": "ato", "decided_days_ago": 210, "ongoing": True},
    },
    {
        "acronym": "FSN", "name": "Field Sensor Network", "environment": "on_prem",
        "confidentiality": "moderate", "integrity": "high", "availability": "high",
        "rmf_step": "assess", "authorizing_official": "Chief Information Officer",
        "description": "On-premises sensor collection and command network supporting field operations.",
        "implemented_share": 0.62,
        "package": {"name": "FY27 initial authorization", "status": "under_assessment", "target_in": 120},
    },
]

STATEMENTS = {
    "AC": "Access is provisioned through the enterprise identity provider with role-based groups; "
          "quarterly access reviews are performed by system owners.",
    "AU": "System and application logs are forwarded to the central SIEM and retained for one year; "
          "alerts are triaged by the SOC.",
    "CM": "Configuration baselines are defined as code and enforced through the deployment pipeline; "
          "drift is reported weekly.",
    "CP": "Backups run nightly with quarterly restore tests; the contingency plan is exercised annually.",
    "IA": "Users authenticate with phishing-resistant MFA; service accounts use short-lived credentials.",
    "IR": "Incidents follow the enterprise incident response plan with defined escalation paths.",
    "RA": "Authenticated vulnerability scans run monthly; findings are tracked to remediation in ICARIS.",
    "SC": "Data in transit uses TLS 1.2+ with FIPS-validated modules; data at rest is encrypted with managed keys.",
    "SI": "Endpoint protection and patching are centrally managed; critical patches follow the expedited process.",
}

POAMS = [
    # system, control, title, priority, days until due (negative = overdue), status, opened days ago
    ("MDP", "ac-2.3", "Disable accounts inactive for more than 35 days", "high", -12, "in_progress", 95),
    ("MDP", "au-6", "Automate weekly audit log review reporting", "medium", 40, "open", 50),
    ("MDP", "si-2", "Remediate outdated TLS library on ingest nodes", "critical", 6, "in_progress", 9),
    ("MDP", "cp-4", "Complete annual contingency plan test", "medium", 90, "open", 20),
    ("HRP", "ia-2.1", "Enforce MFA for vendor support accounts", "high", 20, "open", 40),
    ("FSN", "sc-8", "Encrypt sensor telemetry in transit", "critical", -3, "open", 70),
    ("FSN", "cm-6", "Apply STIG baseline to collection servers", "high", 45, "in_progress", 60),
    ("FSN", "ra-5", "Stand up authenticated vulnerability scanning", "high", 30, "open", 33),
    ("FSN", "ir-4", "Document incident handling procedures for field sites", "medium", 75, "open", 12),
]

# Remediated weaknesses: (system, control, title, priority, opened days ago, closed days ago)
CLOSED_POAMS = [
    ("MDP", "pl-2", "Update SSP to reflect new data ingest pipeline", "low", 150, 120),
    ("MDP", "sc-28", "Enable encryption at rest for analytics snapshots", "high", 170, 110),
    ("HRP", "ac-7", "Lock accounts after repeated failed logins", "medium", 140, 85),
    ("MDP", "au-11", "Extend audit log retention to one year", "medium", 120, 70),
    ("FSN", "cm-8", "Build hardware and software inventory for field sites", "medium", 100, 45),
    ("HRP", "ia-5.1", "Enforce password complexity for local admin accounts", "high", 80, 30),
    ("MDP", "si-4", "Tune SIEM alerts for ingest service anomalies", "medium", 55, 18),
    ("FSN", "pe-3", "Badge access logging at the operations center", "low", 45, 6),
]

CONMON = [
    # title, description, severity, likelihood, impact, compliance %
    ("Monthly authenticated vulnerability scans (RA-5)", "Scan all production assets monthly and review results.", "high", 3, 4, 100),
    ("Weekly audit log review (AU-6)", "Review privileged activity and security alerts weekly.", "medium", 3, 3, 85),
    ("Quarterly access recertification (AC-2)", "System owners recertify user access each quarter.", "high", 2, 4, 60),
    ("Annual contingency plan test (CP-4)", "Exercise the contingency plan and record lessons learned.", "medium", 2, 3, 40),
    ("Configuration baseline drift report (CM-6)", "Compare running configurations against approved baselines.", "medium", 4, 3, 90),
    ("Annual security awareness training (AT-2)", "All users complete training with phishing simulation.", "low", 4, 2, 95),
    ("Incident response tabletop exercise (IR-3)", "Run a tabletop exercise with the SOC and system owners.", "high", 2, 5, 20),
]


def tiny_pdf(title: str) -> bytes:
    """A minimal valid one-page PDF so artifact uploads pass content validation."""
    text = title.replace("(", "[").replace(")", "]")
    stream = f"BT /F1 18 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


class Command(BaseCommand):
    help = "Load realistic demo data (users, systems, ATO packages, POA&Ms, ConMon). Not for production."

    def add_arguments(self, parser):
        parser.add_argument("--password", help="Password for every demo user (default: random, printed once)")
        parser.add_argument("--force", action="store_true", help="Allow running with DEBUG off")

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError("seed_demo creates demo accounts. Run it with DJANGO_DEBUG=true, or pass --force.")
        if not SecurityControl.objects.exists():
            call_command("import_oscal_catalog", stdout=self.stdout)

        password = options["password"] or secrets.token_urlsafe(12)
        # Seeded PRNG for reproducible demo data only; the password above uses secrets.
        rng = random.Random(20261020)  # noqa: S311  # nosec B311
        today = timezone.localdate()

        with transaction.atomic():
            users = self._users(password)
            depts = {
                name: Department.objects.get_or_create(name=name, defaults={"description": desc})[0]
                for name, desc in [
                    ("Security", "Cybersecurity and compliance"),
                    ("IT Operations", "Infrastructure and platform engineering"),
                    ("Human Resources", "People operations"),
                    ("Finance", "Finance and accounting"),
                ]
            }
            systems = self._systems(users, rng, today)
            self._poams(systems, users, depts, today)
            self._conmon(users, depts, today)
            self._audits_and_controls(users, depts, today)
            self._artifacts(users, depts, systems)

        self.stdout.write(self.style.SUCCESS("Demo data loaded."))
        self.stdout.write("Demo logins (all share one password):")
        for username, *_ in DEMO_USERS:
            self.stdout.write(f"  {username}")
        if not options["password"]:
            self.stdout.write(f"Password: {password}")

    # -- helpers -----------------------------------------------------------
    def _users(self, password):
        users = {}
        for username, first, last, role, superuser in DEMO_USERS:
            user, _ = User.objects.get_or_create(username=username)
            user.first_name, user.last_name = first, last
            user.email = f"{username}@example.com"
            user.is_superuser = user.is_staff = superuser
            user.set_password(password)
            user.save()
            if role:
                user.groups.set([Group.objects.get(name=role)])
            users[username] = user
        return users

    def _systems(self, users, rng, today):
        systems = {}
        for spec in SYSTEMS:
            spec = dict(spec)
            package_spec = spec.pop("package")
            share = spec.pop("implemented_share")
            system, created = InformationSystem.objects.update_or_create(
                acronym=spec["acronym"],
                defaults={**spec, "system_owner": users["admin"], "isso": users["isso"]},
            )
            systems[system.acronym] = system
            if not created:
                continue
            ato_services.apply_baseline(system)
            self._fill_implementations(system, share, rng, today)
            self._package(system, package_spec, today)
        return systems

    def _fill_implementations(self, system, share, rng, today):
        updates = []
        for impl in system.implementations.select_related("control__family"):
            family = impl.control.family.code
            roll = rng.random()
            if roll < share:
                impl.status = ControlImplementation.Status.IMPLEMENTED
                impl.assessment_result = "satisfied" if rng.random() < 0.85 else "not_assessed"
                impl.last_assessed = today - timedelta(days=rng.randint(10, 300))
            elif roll < share + (1 - share) * 0.5:
                impl.status = ControlImplementation.Status.PARTIAL
                impl.assessment_result = "other_than_satisfied" if rng.random() < 0.5 else "not_assessed"
            else:
                impl.status = rng.choice([ControlImplementation.Status.PLANNED, ControlImplementation.Status.NOT_STARTED])
            if family in ("PE", "PS", "AT", "PM") and rng.random() < 0.6:
                impl.origination = ControlImplementation.Origination.INHERITED
                impl.inherited_from = "Enterprise common control provider"
            elif rng.random() < 0.2:
                impl.origination = ControlImplementation.Origination.HYBRID
            impl.implementation_statement = STATEMENTS.get(
                family, "Implemented in accordance with the organization's policy for this control family."
            )
            impl.responsible_role = "ISSO" if family in ("CA", "PL", "RA") else "System administrator"
            updates.append(impl)
        ControlImplementation.objects.bulk_update(
            updates,
            ["status", "assessment_result", "last_assessed", "origination", "inherited_from",
             "implementation_statement", "responsible_role"],
        )

    def _package(self, system, spec, today):
        package = ato_services.create_package(system, spec["name"])
        docs = package.documents.all()
        if "decision" in spec:
            package.status = AuthorizationPackage.Status.DECIDED
            package.decision = spec["decision"]
            package.decision_date = today - timedelta(days=spec["decided_days_ago"])
            if spec.get("ongoing"):
                package.ongoing_authorization = True
            else:
                package.expiration_date = today + timedelta(days=spec["expires_in"])
            package.save()
            docs.update(status="approved")
        else:
            package.status = spec["status"]
            package.target_decision_date = today + timedelta(days=spec["target_in"])
            package.save()
            status_by_type = {"categorization": "approved", "ssp": "final", "sap": "approved",
                              "sar": "draft", "poam": "in_review", "cp": "draft", "irp": "final",
                              "cmp": "missing", "conmon": "missing"}
            for doc in docs:
                doc.status = status_by_type.get(doc.doc_type, "missing")
                doc.save(update_fields=["status"])

    def _poams(self, systems, users, depts, today):
        now = timezone.now()
        rows = [(a, c, t, p, due, st, opened, None) for a, c, t, p, due, st, opened in POAMS]
        rows += [(a, c, t, p, opened - closed, "closed", opened, closed) for a, c, t, p, opened, closed in CLOSED_POAMS]
        for acronym, control_id, title, priority, due_in, status, opened_ago, closed_ago in rows:
            control = SecurityControl.objects.get(control_id=control_id)
            issue, created = Issue.objects.get_or_create(
                title=f"{control.label}: {title}",
                defaults={
                    "description": f"Weakness identified against {control.label} {control.title}.",
                    "priority": priority, "status": status,
                    "department": depts["Security"], "assigned_to": users["analyst"],
                    "system": systems[acronym], "control": control,
                    "source": "assessment" if acronym == "FSN" else "conmon",
                    "due_date": today + timedelta(days=due_in) if closed_ago is None
                    else today - timedelta(days=opened_ago) + timedelta(days=due_in + 5),
                    "resolution_notes": "Remediated and verified by ISSO." if closed_ago is not None else "",
                },
            )
            if created:
                # Backdate so the dashboard's monthly activity chart shows history.
                Issue.objects.filter(pk=issue.pk).update(
                    created_at=now - timedelta(days=opened_ago),
                    closed_at=now - timedelta(days=closed_ago) if closed_ago is not None else None,
                )

    def _conmon(self, users, depts, today):
        for title, desc, severity, likelihood, impact, pct in CONMON:
            Risk.objects.get_or_create(
                title=title,
                defaults={
                    "description": desc, "department": depts["Security"], "owner": users["isso"],
                    "severity": severity, "likelihood": likelihood, "impact": impact,
                    "status": "mitigated" if pct >= 80 else "in_progress",
                    "compliance_percentage": pct,
                    "identified_date": today - timedelta(days=60),
                    "target_closure_date": today + timedelta(days=30),
                },
            )

    def _audits_and_controls(self, users, depts, today):
        framework, _ = ComplianceFramework.objects.get_or_create(
            name="NIST SP 800-171", defaults={"description": "Protecting CUI in nonfederal systems", "version": "Rev 2"},
        )
        for control_id, title, status in [
            ("3.1.1", "Limit system access to authorized users", "compliant"),
            ("3.3.1", "Create and retain system audit logs", "compliant"),
            ("3.5.3", "Use multifactor authentication", "in_progress"),
            ("3.11.2", "Scan for vulnerabilities periodically", "compliant"),
            ("3.13.11", "Employ FIPS-validated cryptography", "non_compliant"),
        ]:
            ComplianceControl.objects.get_or_create(
                framework=framework, control_id=control_id,
                defaults={"title": title, "description": title, "department": depts["Security"],
                          "status": status, "owner": users["isso"],
                          "next_assessment_date": today + timedelta(days=120)},
            )
        for title, audit_type, status, start in [
            ("FSN security control assessment", "security", "in_progress", -10),
            ("Annual CMMC readiness review", "compliance", "planned", 25),
            ("MDP ConMon annual review", "internal", "completed", -140),
        ]:
            Audit.objects.get_or_create(
                title=title,
                defaults={"audit_type": audit_type, "department": depts["Security"], "status": status,
                          "auditor": users["auditor"], "scope": title,
                          "start_date": today + timedelta(days=start)},
            )

    def _artifacts(self, users, depts, systems):
        for title, category, acronym, doc_type in [
            ("MDP System Security Plan v4.2", "ato", "MDP", "ssp"),
            ("MDP Security Assessment Report", "ato", "MDP", "sar"),
            ("FSN System Security Plan (draft)", "ato", "FSN", "ssp"),
            ("Incident Response Plan", "policy", None, None),
            ("Q3 vulnerability scan summary", "evidence", None, None),
        ]:
            if Artifact.objects.filter(title=title).exists():
                continue
            artifact = Artifact(title=title, category=category, department=depts["Security"],
                                uploaded_by=users["isso"], original_filename=f"{title}.pdf")
            artifact.file.save(f"{title}.pdf", ContentFile(tiny_pdf(title)), save=True)
            if acronym:
                package = systems[acronym].packages.first()
                package.documents.filter(doc_type=doc_type).update(artifact=artifact)
