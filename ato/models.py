"""
ATO tracking: information systems, their NIST SP 800-53 control
implementations, and the authorization packages that lead to an ATO.

Terminology follows NIST SP 800-37 Rev 2 (RMF), FIPS 199 (security
categorization) and the OSCAL/FedRAMP SSP vocabulary for implementation
status and control origination.
"""
from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

IMPACT_LEVELS = [("low", "Low"), ("moderate", "Moderate"), ("high", "High")]
_IMPACT_RANK = {"low": 1, "moderate": 2, "high": 3}


class ControlFamily(models.Model):
    code = models.CharField(max_length=4, unique=True)  # "AC"
    title = models.CharField(max_length=100)             # "Access Control"

    class Meta:
        ordering = ["code"]
        verbose_name_plural = "control families"

    def __str__(self):
        return f"{self.code} - {self.title}"


class SecurityControl(models.Model):
    """One control or enhancement from the NIST SP 800-53 catalog."""

    control_id = models.CharField(max_length=20, unique=True)  # OSCAL id: "ac-2.1"
    label = models.CharField(max_length=20)                    # "AC-2(1)"
    title = models.CharField(max_length=255)
    family = models.ForeignKey(ControlFamily, on_delete=models.CASCADE, related_name="controls")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="enhancements")
    sort_key = models.CharField(max_length=30, db_index=True)
    statement = models.TextField(blank=True)
    withdrawn = models.BooleanField(default=False)
    in_low = models.BooleanField("Low baseline", default=False)
    in_moderate = models.BooleanField("Moderate baseline", default=False)
    in_high = models.BooleanField("High baseline", default=False)
    catalog_version = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["sort_key"]

    def __str__(self):
        return f"{self.label} {self.title}"

    @property
    def is_enhancement(self) -> bool:
        return self.parent_id is not None

    @classmethod
    def baseline_queryset(cls, level: str):
        field = {"low": "in_low", "moderate": "in_moderate", "high": "in_high"}[level]
        return cls.objects.filter(**{field: True}, withdrawn=False)


class InformationSystem(models.Model):
    class RmfStep(models.TextChoices):
        PREPARE = "prepare", "Prepare"
        CATEGORIZE = "categorize", "Categorize"
        SELECT = "select", "Select"
        IMPLEMENT = "implement", "Implement"
        ASSESS = "assess", "Assess"
        AUTHORIZE = "authorize", "Authorize"
        MONITOR = "monitor", "Monitor"

    class Environment(models.TextChoices):
        ON_PREM = "on_prem", "On-premises"
        CLOUD = "cloud", "Cloud"
        HYBRID = "hybrid", "Hybrid"

    name = models.CharField(max_length=200)
    acronym = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)
    environment = models.CharField(max_length=20, choices=Environment.choices, default=Environment.ON_PREM)
    confidentiality = models.CharField(max_length=10, choices=IMPACT_LEVELS, default="moderate")
    integrity = models.CharField(max_length=10, choices=IMPACT_LEVELS, default="moderate")
    availability = models.CharField(max_length=10, choices=IMPACT_LEVELS, default="moderate")
    rmf_step = models.CharField("RMF step", max_length=20, choices=RmfStep.choices, default=RmfStep.PREPARE)
    system_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="owned_systems"
    )
    isso = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="isso_systems", verbose_name="ISSO",
    )
    authorizing_official = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["acronym"]

    def __str__(self):
        return f"{self.acronym} - {self.name}"

    def get_absolute_url(self):
        return reverse("ato:system_detail", args=[self.pk])

    @property
    def categorization(self) -> str:
        """FIPS 199 / FIPS 200 high-water mark across C, I and A."""
        return max((self.confidentiality, self.integrity, self.availability), key=_IMPACT_RANK.__getitem__)

    def get_categorization_display(self) -> str:
        return dict(IMPACT_LEVELS)[self.categorization]

    @property
    def current_authorization(self):
        """Most recent package that reached a decision."""
        return (
            self.packages.exclude(decision_date__isnull=True)
            .order_by("-decision_date", "-pk")
            .first()
        )

    def implementation_summary(self) -> dict:
        counts = self.implementations.aggregate(
            total=Count("id"),
            implemented=Count("id", filter=Q(status=ControlImplementation.Status.IMPLEMENTED)),
            not_applicable=Count("id", filter=Q(status=ControlImplementation.Status.NOT_APPLICABLE)),
            partial=Count("id", filter=Q(status=ControlImplementation.Status.PARTIAL)),
            planned=Count("id", filter=Q(status=ControlImplementation.Status.PLANNED)),
            not_started=Count("id", filter=Q(status=ControlImplementation.Status.NOT_STARTED)),
            satisfied=Count("id", filter=Q(assessment_result=ControlImplementation.Result.SATISFIED)),
            other_than_satisfied=Count("id", filter=Q(assessment_result=ControlImplementation.Result.OTHER_THAN_SATISFIED)),
        )
        applicable = counts["total"] - counts["not_applicable"]
        counts["percent_implemented"] = round(100 * counts["implemented"] / applicable) if applicable else 0
        return counts


class ControlImplementation(models.Model):
    """How one system implements one control (an SSP control entry)."""

    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Not started"
        PLANNED = "planned", "Planned"
        PARTIAL = "partial", "Partially implemented"
        IMPLEMENTED = "implemented", "Implemented"
        ALTERNATIVE = "alternative", "Alternative implementation"
        NOT_APPLICABLE = "not_applicable", "Not applicable"

    class Origination(models.TextChoices):
        SYSTEM = "system", "System-specific"
        HYBRID = "hybrid", "Hybrid"
        INHERITED = "inherited", "Inherited (common control)"

    class Result(models.TextChoices):
        NOT_ASSESSED = "not_assessed", "Not assessed"
        SATISFIED = "satisfied", "Satisfied"
        OTHER_THAN_SATISFIED = "other_than_satisfied", "Other than satisfied"

    system = models.ForeignKey(InformationSystem, on_delete=models.CASCADE, related_name="implementations")
    control = models.ForeignKey(SecurityControl, on_delete=models.PROTECT, related_name="implementations")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOT_STARTED)
    origination = models.CharField(max_length=20, choices=Origination.choices, default=Origination.SYSTEM)
    inherited_from = models.CharField(max_length=200, blank=True, help_text="Common control provider, if inherited")
    responsible_role = models.CharField(max_length=100, blank=True)
    implementation_statement = models.TextField(blank=True)
    assessment_result = models.CharField(max_length=30, choices=Result.choices, default=Result.NOT_ASSESSED)
    last_assessed = models.DateField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["control__sort_key"]
        constraints = [
            models.UniqueConstraint(fields=["system", "control"], name="unique_control_per_system"),
        ]

    def __str__(self):
        return f"{self.system.acronym} {self.control.label}"

    def clean(self):
        if self.status == self.Status.NOT_APPLICABLE and not self.implementation_statement.strip():
            raise ValidationError({"implementation_statement": "Explain why the control is not applicable."})
        if self.origination == self.Origination.INHERITED and not self.inherited_from.strip():
            raise ValidationError({"inherited_from": "Name the common control provider."})


class AuthorizationPackage(models.Model):
    """An assessment-and-authorization cycle for one system."""

    class Status(models.TextChoices):
        IN_PREPARATION = "in_preparation", "In preparation"
        UNDER_ASSESSMENT = "under_assessment", "Under assessment"
        SUBMITTED = "submitted", "Submitted to AO"
        DECIDED = "decided", "Decision issued"

    class Decision(models.TextChoices):
        ATO = "ato", "Authorization to Operate (ATO)"
        ATO_CONDITIONS = "ato_conditions", "ATO with conditions"
        IATT = "iatt", "Interim Authorization to Test (IATT)"
        ATU = "atu", "Authorization to Use (ATU)"
        DATO = "dato", "Denial of Authorization (DATO)"

    AUTHORIZING_DECISIONS = {Decision.ATO, Decision.ATO_CONDITIONS, Decision.IATT, Decision.ATU}

    system = models.ForeignKey(InformationSystem, on_delete=models.CASCADE, related_name="packages")
    name = models.CharField(max_length=200, help_text="e.g. 'FY27 initial authorization'")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_PREPARATION)
    target_decision_date = models.DateField(null=True, blank=True)
    decision = models.CharField(max_length=20, choices=Decision.choices, blank=True)
    decision_date = models.DateField(null=True, blank=True)
    expiration_date = models.DateField(null=True, blank=True, help_text="Authorization termination date")
    ongoing_authorization = models.BooleanField(
        default=False, help_text="Authorized under continuous monitoring with no fixed termination date"
    )
    conditions = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.system.acronym}: {self.name}"

    def get_absolute_url(self):
        return reverse("ato:package_detail", args=[self.pk])

    def clean(self):
        errors = {}
        if self.status == self.Status.DECIDED:
            if not self.decision:
                errors["decision"] = "Record the decision once one has been issued."
            if not self.decision_date:
                errors["decision_date"] = "Record the decision date."
        if self.decision in self.AUTHORIZING_DECISIONS and self.decision != self.Decision.ATU:
            if not self.expiration_date and not self.ongoing_authorization:
                errors["expiration_date"] = "Set a termination date or mark the authorization as ongoing."
        if self.decision == self.Decision.ATO_CONDITIONS and not self.conditions.strip():
            errors["conditions"] = "List the conditions attached to the authorization."
        if self.expiration_date and self.decision_date and self.expiration_date <= self.decision_date:
            errors["expiration_date"] = "Termination date must be after the decision date."
        if errors:
            raise ValidationError(errors)

    @property
    def is_authorized(self) -> bool:
        if self.decision not in self.AUTHORIZING_DECISIONS:
            return False
        return self.ongoing_authorization or self.expiration_date is None or self.expiration_date >= timezone.localdate()

    @property
    def days_until_expiration(self) -> int | None:
        if not self.expiration_date or self.ongoing_authorization:
            return None
        return (self.expiration_date - timezone.localdate()).days

    @property
    def expiry_state(self) -> str:
        """ok / warning (<=180 days) / critical (<=90 days) / expired / none."""
        days = self.days_until_expiration
        if days is None:
            return "none"
        if days < 0:
            return "expired"
        if days <= 90:
            return "critical"
        if days <= 180:
            return "warning"
        return "ok"

    def readiness(self) -> dict:
        docs = list(self.documents.all())
        required = [d for d in docs if d.required]
        done = [d for d in required if d.status in (PackageDocument.Status.FINAL, PackageDocument.Status.APPROVED)]
        return {
            "required": len(required),
            "complete": len(done),
            "percent": round(100 * len(done) / len(required)) if required else 0,
        }


class PackageDocument(models.Model):
    """A document the authorization package needs, tracked through to approval."""

    class DocType(models.TextChoices):
        SSP = "ssp", "System Security Plan (SSP)"
        SAP = "sap", "Security Assessment Plan (SAP)"
        SAR = "sar", "Security Assessment Report (SAR)"
        POAM = "poam", "Plan of Action & Milestones (POA&M)"
        CATEGORIZATION = "categorization", "Security categorization (FIPS 199)"
        PIA = "pia", "Privacy Impact Assessment (PIA)"
        CP = "cp", "Contingency Plan (CP)"
        IRP = "irp", "Incident Response Plan (IRP)"
        CMP = "cmp", "Configuration Management Plan (CMP)"
        CONMON = "conmon", "Continuous Monitoring Strategy"
        ISA = "isa", "Interconnection Security Agreement (ISA)"
        AUTH_LETTER = "auth_letter", "Authorization decision document"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        MISSING = "missing", "Missing"
        DRAFT = "draft", "Draft"
        IN_REVIEW = "in_review", "In review"
        FINAL = "final", "Final"
        APPROVED = "approved", "Approved"

    # Core package contents; added automatically to every new package.
    DEFAULT_REQUIRED = [
        DocType.CATEGORIZATION, DocType.SSP, DocType.SAP, DocType.SAR,
        DocType.POAM, DocType.CP, DocType.IRP, DocType.CMP, DocType.CONMON,
    ]

    package = models.ForeignKey(AuthorizationPackage, on_delete=models.CASCADE, related_name="documents")
    doc_type = models.CharField(max_length=20, choices=DocType.choices)
    required = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.MISSING)
    artifact = models.ForeignKey(
        "grc_dashboard.Artifact", null=True, blank=True, on_delete=models.SET_NULL, related_name="package_documents"
    )
    notes = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["package", "doc_type"]
        constraints = [
            models.UniqueConstraint(
                fields=["package", "doc_type"], condition=~Q(doc_type="other"), name="one_of_each_doc_type"
            ),
        ]

    def __str__(self):
        return f"{self.package} - {self.get_doc_type_display()}"


def systems_expiring(within_days: int = 180, today: date | None = None):
    """Current authorizations that end within the window (or have already ended).

    Only each system's most recent decision counts, so a renewed system does
    not show up because of an older, superseded package.
    """
    today = today or timezone.localdate()
    results = []
    for system in InformationSystem.objects.prefetch_related("packages"):
        current = system.current_authorization
        if (
            current
            and current.decision in AuthorizationPackage.AUTHORIZING_DECISIONS
            and not current.ongoing_authorization
            and current.expiration_date
            and (current.expiration_date - today).days <= within_days
        ):
            results.append(current)
    return sorted(results, key=lambda p: p.expiration_date)
