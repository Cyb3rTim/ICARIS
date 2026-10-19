# grc_dashboard/models.py
from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .validators import RandomizedUploadPath, validate_evidence_file


class Department(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class Risk(models.Model):
    SEVERITY_CHOICES = [
        ('critical', 'Critical'),
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    ]

    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('mitigated', 'Mitigated'),
        ('accepted', 'Accepted'),
        ('closed', 'Closed'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField()
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='risks')
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    likelihood = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Likelihood score (1-5)"
    )
    impact = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Impact score (1-5)"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='owned_risks')
    mitigation_plan = models.TextField(blank=True)
    identified_date = models.DateField(default=timezone.now)
    target_closure_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Compliance tracking fields
    compliance_percentage = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Compliance percentage (0-100%)",
        verbose_name="Compliance %"
    )

    evidence_uploaded = models.BooleanField(
        default=False,
        help_text="Has compliance evidence been uploaded?",
        verbose_name="Evidence Uploaded"
    )

    evidence_file = models.FileField(
        upload_to=RandomizedUploadPath('compliance_evidence'),
        validators=[validate_evidence_file],
        null=True,
        blank=True,
        help_text="Compliance evidence file",
        verbose_name="Evidence File"
    )

    last_evidence_update = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time evidence was updated",
        verbose_name="Last Evidence Update"
    )

    @property
    def risk_score(self):
        return self.likelihood * self.impact

    def get_compliance_status(self):
        """Returns Compliant or Non-Compliant based on percentage"""
        return "Compliant" if self.compliance_percentage >= 80 else "Non-Compliant"

    def get_compliance_color_class(self):
        """Returns CSS class based on compliance percentage"""
        if self.compliance_percentage >= 80:
            return "high"  # Green
        elif self.compliance_percentage >= 50:
            return "medium"  # Orange
        else:
            return "low"  # Red

    def update_compliance_from_evidence(self):
        """Update compliance percentage when evidence is uploaded"""
        if self.evidence_uploaded and self.evidence_file:
            self.compliance_percentage = 100
            self.last_evidence_update = timezone.now()
            self.save()
        else:
            self.compliance_percentage = 0
            self.save()

    def __str__(self):
        return f"{self.title} ({self.severity})"

    class Meta:
        ordering = ['-created_at']


class ComplianceFramework(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    version = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class ComplianceControl(models.Model):
    STATUS_CHOICES = [
        ('compliant', 'Compliant'),
        ('non_compliant', 'Non-Compliant'),
        ('in_progress', 'In Progress'),
        ('not_assessed', 'Not Assessed'),
    ]

    framework = models.ForeignKey(ComplianceFramework, on_delete=models.CASCADE, related_name='controls')
    control_id = models.CharField(max_length=50)
    title = models.CharField(max_length=200)
    description = models.TextField()
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='compliance_controls')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='not_assessed')
    owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='owned_controls')
    evidence = models.TextField(blank=True, help_text="Evidence of compliance")
    last_assessment_date = models.DateField(null=True, blank=True)
    next_assessment_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.control_id}: {self.title}"

    class Meta:
        ordering = ['framework', 'control_id']
        unique_together = ['framework', 'control_id']


class Audit(models.Model):
    TYPE_CHOICES = [
        ('internal', 'Internal Audit'),
        ('external', 'External Audit'),
        ('compliance', 'Compliance Review'),
        ('security', 'Security Audit'),
    ]

    STATUS_CHOICES = [
        ('planned', 'Planned'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    title = models.CharField(max_length=200)
    audit_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='audits')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planned')
    auditor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='audits_conducted')
    scope = models.TextField()
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    findings = models.TextField(blank=True)
    recommendations = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"

    class Meta:
        ordering = ['-start_date']


class Issue(models.Model):
    PRIORITY_CHOICES = [
        ('critical', 'Critical'),
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    ]

    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField()
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='issues')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_issues')
    related_risk = models.ForeignKey(Risk, on_delete=models.SET_NULL, null=True, blank=True, related_name='issues')
    related_audit = models.ForeignKey(Audit, on_delete=models.SET_NULL, null=True, blank=True, related_name='issues')
    system = models.ForeignKey(
        'ato.InformationSystem', on_delete=models.SET_NULL, null=True, blank=True, related_name='poams',
        help_text="Information system the weakness belongs to",
    )
    control = models.ForeignKey(
        'ato.SecurityControl', on_delete=models.SET_NULL, null=True, blank=True, related_name='poams',
        help_text="NIST SP 800-53 control the weakness relates to",
    )
    source = models.CharField(
        max_length=20,
        choices=[
            ('assessment', 'Security assessment'),
            ('scan', 'Vulnerability scan'),
            ('conmon', 'Continuous monitoring'),
            ('audit', 'Audit'),
            ('other', 'Other'),
        ],
        default='assessment',
        help_text="How the weakness was identified",
    )
    due_date = models.DateField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} ({self.priority})"

    class Meta:
        ordering = ['-created_at']


class Artifact(models.Model):
    CATEGORY_CHOICES = [
        ('ato', 'ATO'),
        ('certification', 'Certification'),
        ('diagram', 'Diagram'),
        ('evidence', 'Evidence'),
        ('other', 'Other'),
        ('policy', 'Policy'),
        ('procedure', 'Procedure'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='artifacts')
    file = models.FileField(
        upload_to=RandomizedUploadPath('artifacts'),
        validators=[validate_evidence_file],
    )
    original_filename = models.CharField(max_length=255, blank=True, editable=False)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='uploaded_artifacts')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    @property
    def file_extension(self):
        return self.file.name.split('.')[-1].lower() if self.file else ''

    @property
    def file_size_mb(self):
        if self.file:
            return round(self.file.size / (1024 * 1024), 2)
        return 0

    class Meta:
        ordering = ['-created_at']


class UserProfile(models.Model):
    """Extended user profile with department and role information"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.department if self.department else 'No Department'}"

    def can_manage_poams(self):
        """True if the user may create, edit and delete PO&AMs (see roles.py)."""
        return self.user.has_perms(
            ["grc_dashboard.add_issue", "grc_dashboard.change_issue", "grc_dashboard.delete_issue"]
        )


# Auto-create profile when user is created
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()
