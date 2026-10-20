# grc_dashboard/views.py
import csv
from collections import Counter
from datetime import date, datetime, time

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Avg, Count, Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from . import audit_log
from .forms import IssueForm, RiskForm
from .models import Artifact, Audit, ComplianceControl, Department, Issue, Risk


def _month_starts(today, count=6):
    """First day of each of the last `count` months, oldest first."""
    months = []
    year, month = today.year, today.month
    for _ in range(count):
        months.append(date(year, month, 1))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(months))


@login_required
def dashboard(request):
    """Executive dashboard: portfolio ATO posture and POA&M health, all from live data."""
    from ato.models import ControlImplementation
    from ato.services import ato_summary

    today = timezone.localdate()
    active = ['open', 'in_progress']

    impl = ControlImplementation.objects.aggregate(
        total=Count('id'),
        implemented=Count('id', filter=Q(status=ControlImplementation.Status.IMPLEMENTED)),
        not_applicable=Count('id', filter=Q(status=ControlImplementation.Status.NOT_APPLICABLE)),
    )
    applicable = impl['total'] - impl['not_applicable']
    percent_implemented = round(100 * impl['implemented'] / applicable) if applicable else 0

    open_poams = Issue.objects.filter(status__in=active)
    portfolio = ato_summary()

    # POA&M activity: opened vs closed per month for the last six months.
    months = _month_starts(today)
    window_start = timezone.make_aware(datetime.combine(months[0], time.min))
    opened = Counter(
        timezone.localtime(ts).date().replace(day=1)
        for ts in Issue.objects.filter(created_at__gte=window_start).values_list('created_at', flat=True)
    )
    closed = Counter(
        timezone.localtime(ts).date().replace(day=1)
        for ts in Issue.objects.filter(closed_at__gte=window_start).values_list('closed_at', flat=True)
    )
    activity = {
        'labels': [m.strftime('%b') for m in months],
        'opened': [opened.get(m, 0) for m in months],
        'closed': [closed.get(m, 0) for m in months],
    }

    by_priority = dict(open_poams.values_list('priority').annotate(n=Count('id')))
    priority = {
        'labels': ['Low', 'Medium', 'High', 'Critical'],
        'counts': [by_priority.get(p, 0) for p in ('low', 'medium', 'high', 'critical')],
    }

    context = {
        'percent_implemented': percent_implemented,
        'controls_tracked': impl['total'],
        'open_poam_count': open_poams.count(),
        'overdue_poam_count': open_poams.filter(due_date__lt=today).count(),
        'systems': portfolio['systems'],
        'authorized': portfolio['authorized'],
        'expiring': portfolio['expiring'],
        'activity': activity,
        'priority': priority,
        'upcoming_poams': open_poams.select_related('system', 'control')
            .exclude(due_date__isnull=True).order_by('due_date')[:8],
    }
    return render(request, 'grc_dashboard/dashboard.html', context)


COMPLIANT_THRESHOLD = 80


@login_required
def risk_register(request):
    """ConMon requirement register with compliance filters and heat map."""
    all_risks = Risk.objects.select_related('department', 'owner')
    risks = all_risks

    status_filter = request.GET.get('status')
    compliance_filter = request.GET.get('compliance')
    department_filter = request.GET.get('department')

    if status_filter == 'Compliant':
        risks = risks.filter(compliance_percentage__gte=COMPLIANT_THRESHOLD)
    elif status_filter == 'Non-Compliant':
        risks = risks.filter(compliance_percentage__lt=COMPLIANT_THRESHOLD)

    if compliance_filter == 'high':
        risks = risks.filter(compliance_percentage__gte=80)
    elif compliance_filter == 'medium':
        risks = risks.filter(compliance_percentage__gte=50, compliance_percentage__lt=80)
    elif compliance_filter == 'low':
        risks = risks.filter(compliance_percentage__lt=50)

    if department_filter and department_filter.isdigit():
        risks = risks.filter(department_id=department_filter)

    avg = all_risks.aggregate(avg=Avg('compliance_percentage'))['avg'] or 0
    heatmap = [
        {'likelihood': r.likelihood, 'impact': r.impact}
        for r in risks
    ]

    context = {
        'risks': risks,
        'departments': Department.objects.all(),
        'status_filter': status_filter,
        'department_filter': department_filter,
        'total_risks': all_risks.count(),
        'compliant_count': all_risks.filter(compliance_percentage__gte=COMPLIANT_THRESHOLD).count(),
        'noncompliant_count': all_risks.filter(compliance_percentage__lt=COMPLIANT_THRESHOLD).count(),
        'avg_compliance': round(avg),
        'heatmap_data': heatmap,
    }

    return render(request, 'grc_dashboard/risk_register.html', context)


@login_required
def risk_heatmap_data(request):
    """API endpoint for risk heatmap data"""
    risks = Risk.objects.all()

    data = []
    for risk in risks:
        data.append({
            'id': risk.id,
            'title': risk.title,
            'likelihood': risk.likelihood,
            'impact': risk.impact,
            'severity': risk.severity,
            'department': risk.department.name,
        })

    return JsonResponse({'risks': data})


@login_required
def compliance_tracking(request):
    """Compliance tracking view"""
    controls = ComplianceControl.objects.select_related('framework', 'department', 'owner').all()

    # Apply filters
    framework_filter = request.GET.get('framework')
    status_filter = request.GET.get('status')

    if framework_filter:
        controls = controls.filter(framework_id=framework_filter)
    if status_filter:
        controls = controls.filter(status=status_filter)

    from .models import ComplianceFramework
    frameworks = ComplianceFramework.objects.all()

    context = {
        'controls': controls,
        'frameworks': frameworks,
        'framework_filter': framework_filter,
        'status_filter': status_filter,
    }

    return render(request, 'grc_dashboard/compliance_tracking.html', context)


@login_required
def audit_management(request):
    """Audit management view"""
    audits = Audit.objects.select_related('department', 'auditor').all()

    # Apply filters
    type_filter = request.GET.get('type')
    status_filter = request.GET.get('status')

    if type_filter:
        audits = audits.filter(audit_type=type_filter)
    if status_filter:
        audits = audits.filter(status=status_filter)

    context = {
        'audits': audits,
        'type_filter': type_filter,
        'status_filter': status_filter,
    }

    return render(request, 'grc_dashboard/audit_management.html', context)


@login_required
def issue_tracking(request):
    """POA&M list with filters and live status counts."""
    all_issues = Issue.objects.select_related('department', 'assigned_to', 'system', 'control')
    issues = all_issues

    priority_filter = request.GET.get('priority')
    status_filter = request.GET.get('status')
    department_filter = request.GET.get('department')

    if priority_filter:
        issues = issues.filter(priority=priority_filter)
    if status_filter:
        issues = issues.filter(status=status_filter)
    if department_filter and department_filter.isdigit():
        issues = issues.filter(department_id=department_filter)

    today = timezone.now().date()
    active = ['open', 'in_progress']
    context = {
        'issues': issues,
        'departments': Department.objects.all(),
        'priority_filter': priority_filter,
        'status_filter': status_filter,
        'department_filter': department_filter,
        'today': today,
        'stats': {
            'total': all_issues.count(),
            'open': all_issues.filter(status__in=active).count(),
            'resolved': all_issues.filter(status__in=['resolved', 'closed']).count(),
            'overdue': all_issues.filter(status__in=active, due_date__lt=today).count(),
        },
    }

    return render(request, 'grc_dashboard/issue_tracking.html', context)


@login_required
@permission_required('grc_dashboard.add_risk', raise_exception=True)
def risk_create(request):
    """Create a new ConMon requirement"""
    if request.method == 'POST':
        form = RiskForm(request.POST, request.FILES)
        if form.is_valid():
            risk = form.save(commit=False)

            # If evidence file is uploaded, mark as uploaded
            if 'evidence_file' in request.FILES:
                risk.evidence_uploaded = True
                risk.last_evidence_update = timezone.now()

            risk.save()
            audit_log.record(request, 'create', risk)
            messages.success(request, 'ConMon requirement created successfully!')
            return redirect('risk_register')
    else:
        form = RiskForm()

    return render(request, 'grc_dashboard/risk_form.html', {
        'form': form,
        'action': 'Create'
    })


@login_required
@permission_required('grc_dashboard.change_risk', raise_exception=True)
def risk_update(request, pk):
    """Update/Edit a ConMon requirement"""
    risk = get_object_or_404(Risk, pk=pk)

    if request.method == 'POST':
        form = RiskForm(request.POST, request.FILES, instance=risk)
        if form.is_valid():
            risk = form.save(commit=False)
            if 'evidence_file' in request.FILES:
                risk.evidence_uploaded = True
                risk.last_evidence_update = timezone.now()
            risk.save()
            audit_log.record(request, 'update', risk)
            messages.success(request, 'ConMon requirement updated.')
            return redirect('risk_register')
    else:
        form = RiskForm(instance=risk)

    return render(request, 'grc_dashboard/risk_form.html', {'form': form, 'action': 'Update', 'risk': risk})


@login_required
@permission_required('grc_dashboard.delete_risk', raise_exception=True)
def risk_delete(request, pk):
    """Delete a ConMon requirement"""
    risk = get_object_or_404(Risk, pk=pk)

    if request.method == 'POST':
        audit_log.record(request, 'delete', risk)
        risk.delete()
        return redirect('risk_register')

    return render(request, 'grc_dashboard/risk_confirm_delete.html', {'risk': risk})


@login_required
def artifacts(request):
    """Artifacts document management view with filtering and statistics"""

    # Get all artifacts
    artifacts_list = Artifact.objects.select_related('department', 'uploaded_by').all()

    # Apply filters
    category_filter = request.GET.get('category')
    department_filter = request.GET.get('department')

    if category_filter:
        artifacts_list = artifacts_list.filter(category=category_filter)
    if department_filter:
        artifacts_list = artifacts_list.filter(department_id=department_filter)

    # Get all departments for filter dropdown
    departments = Department.objects.all()

    # Calculate statistics by category
    all_artifacts = Artifact.objects.all()
    stats = {
        'total': all_artifacts.count(),
        'policy': all_artifacts.filter(category='policy').count(),
        'certification': all_artifacts.filter(category='certification').count(),
        'evidence': all_artifacts.filter(category='evidence').count(),
        'documents': all_artifacts.filter(category__in=['policy', 'procedure']).count(),
    }

    context = {
        'artifacts': artifacts_list,
        'departments': departments,
        'stats': stats,
        'category_filter': category_filter,
        'department_filter': department_filter,
    }

    return render(request, 'grc_dashboard/artifacts.html', context)


@login_required
@permission_required('grc_dashboard.add_issue', raise_exception=True)
def issue_create(request):
    if request.method == 'POST':
        form = IssueForm(request.POST)
        if form.is_valid():
            issue = form.save(commit=False)
            if not issue.assigned_to:
                issue.assigned_to = request.user
            issue.save()
            audit_log.record(request, 'create', issue)
            messages.success(request, 'POA&M created.')
            return redirect('issue_tracking')
    else:
        form = IssueForm()

    return render(request, 'grc_dashboard/issue_form.html', {'form': form, 'action': 'Create'})


@login_required
@permission_required('grc_dashboard.change_issue', raise_exception=True)
def issue_update(request, pk):
    issue = get_object_or_404(Issue, pk=pk)

    if request.method == 'POST':
        form = IssueForm(request.POST, instance=issue)
        if form.is_valid():
            form.save()
            audit_log.record(request, 'update', issue)
            messages.success(request, 'POA&M updated.')
            return redirect('issue_tracking')
    else:
        form = IssueForm(instance=issue)

    return render(request, 'grc_dashboard/issue_form.html', {'form': form, 'action': 'Update', 'issue': issue})


@login_required
@permission_required('grc_dashboard.delete_issue', raise_exception=True)
def issue_delete(request, pk):
    issue = get_object_or_404(Issue, pk=pk)

    if request.method == 'POST':
        audit_log.record(request, 'delete', issue)
        issue.delete()
        return redirect('issue_tracking')

    return render(request, 'grc_dashboard/issue_confirm_delete.html', {'issue': issue})


@login_required
@permission_required('grc_dashboard.add_artifact', raise_exception=True)
def artifact_create(request):
    """Upload a new artifact"""
    from .forms import ArtifactForm

    if request.method == 'POST':
        form = ArtifactForm(request.POST, request.FILES)
        if form.is_valid():
            artifact = form.save(commit=False)
            artifact.uploaded_by = request.user
            artifact.original_filename = request.FILES['file'].name[:255]
            artifact.save()
            audit_log.record(request, 'create', artifact)

            messages.success(
                request,
                f'✅ {artifact.get_category_display()} uploaded successfully!'
            )

            return redirect('artifacts')
    else:
        form = ArtifactForm()

    return render(request, 'grc_dashboard/artifact_form.html', {
        'form': form,
        'action': 'Upload'
    })


@login_required
@permission_required('grc_dashboard.delete_artifact', raise_exception=True)
def artifact_delete(request, pk):
    artifact = get_object_or_404(Artifact, pk=pk)

    if request.method == 'POST':
        audit_log.record(request, 'delete', artifact)
        artifact.file.delete()
        artifact.delete()
        return redirect('artifacts')

    return render(request, 'grc_dashboard/artifact_confirm_delete.html', {'artifact': artifact})


INLINE_SAFE_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "txt"}


def _serve_protected_file(request, field_file, download_name):
    """Stream a stored upload to an authenticated user.

    Uploaded files are never served from a public /media/ URL. Only formats a
    browser renders safely may open inline; everything else downloads.
    """
    if not field_file:
        raise Http404("No file attached.")
    try:
        handle = field_file.open("rb")
    except FileNotFoundError as exc:
        raise Http404("File is missing from storage.") from exc
    ext = field_file.name.rsplit(".", 1)[-1].lower() if "." in field_file.name else ""
    inline = request.GET.get("inline") == "1" and ext in INLINE_SAFE_EXTENSIONS
    response = FileResponse(handle, as_attachment=not inline, filename=download_name)
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
@require_GET
def artifact_download(request, pk):
    artifact = get_object_or_404(Artifact, pk=pk)
    name = artifact.original_filename or f"{artifact.title}.{artifact.file_extension}"
    audit_log.record(request, 'download', artifact)
    return _serve_protected_file(request, artifact.file, name)


@login_required
@require_GET
def risk_evidence_download(request, pk):
    risk = get_object_or_404(Risk, pk=pk)
    ext = risk.evidence_file.name.rsplit(".", 1)[-1] if risk.evidence_file else ""
    audit_log.record(request, 'download', risk)
    return _serve_protected_file(request, risk.evidence_file, f"conmon-{risk.pk}-evidence.{ext}")


POAM_EXPORT_COLUMNS = [
    "POA&M ID", "System", "Control", "Weakness", "Description", "Source", "Priority",
    "Status", "Assigned To", "Scheduled Completion", "Overdue", "Closed", "Resolution Notes", "Created",
]


def _csv_safe(value) -> str:
    """Neutralize spreadsheet formula injection (CWE-1236) in exported cells."""
    text = "" if value is None else str(value)
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


@login_required
@require_GET
def poam_export(request):
    """Download all POA&Ms (respecting the list filters) as CSV."""
    issues = Issue.objects.select_related("system", "control", "assigned_to").order_by("pk")
    for param, field in (("priority", "priority"), ("status", "status")):
        if request.GET.get(param):
            issues = issues.filter(**{field: request.GET[param]})
    if request.GET.get("department", "").isdigit():
        issues = issues.filter(department_id=request.GET["department"])

    stamp = timezone.localdate().isoformat()
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="icaris-poams-{stamp}.csv"'
    response["Cache-Control"] = "private, no-store"
    writer = csv.writer(response)
    writer.writerow(POAM_EXPORT_COLUMNS)
    for issue in issues:
        writer.writerow([_csv_safe(v) for v in (
            f"POAM-{issue.pk:04d}",
            issue.system.acronym if issue.system else "",
            issue.control.label if issue.control else "",
            issue.title,
            issue.description,
            issue.get_source_display(),
            issue.get_priority_display(),
            issue.get_status_display(),
            issue.assigned_to.get_full_name() or issue.assigned_to.username if issue.assigned_to else "",
            issue.due_date.isoformat() if issue.due_date else "",
            "Yes" if issue.is_overdue else "No",
            timezone.localtime(issue.closed_at).date().isoformat() if issue.closed_at else "",
            issue.resolution_notes,
            timezone.localtime(issue.created_at).date().isoformat(),
        )])
    audit_log.record(request, "export", Issue())
    return response


def user_guide(request):
    """Display the user guide"""
    context = {
        'page_title': 'User Guide',
        'guide_sections': [
            {
                'id': 'getting-started',
                'title': 'Getting Started',
                'icon': 'fas fa-play-circle',
                'description': 'Learn the basics of navigating the GRC Hub'
            },
            {
                'id': 'risk-management',
                'title': 'Risk Management',
                'icon': 'fas fa-exclamation-triangle',
                'description': 'How to create and manage risks'
            },
            {
                'id': 'compliance',
                'title': 'Compliance Tracking',
                'icon': 'fas fa-check-circle',
                'description': 'Track and monitor compliance requirements'
            },
            {
                'id': 'audits',
                'title': 'Audit Management',
                'icon': 'fas fa-clipboard-check',
                'description': 'Manage audits and findings'
            },
            {
                'id': 'issues',
                'title': 'Issue Tracking',
                'icon': 'fas fa-tasks',
                'description': 'Track and resolve issues'
            }
        ]
    }
    return render(request, 'grc_dashboard/user_guide.html', context)


@require_POST
def user_logout(request):
    """Log out (POST only, CSRF-protected) and return to the login page.

    Accepting GET would let any page log a user out with an <img> tag.
    """
    username = request.user.username if request.user.is_authenticated else "User"
    logout(request)
    messages.success(request, f"Goodbye {username}! You have been successfully logged out.")
    return redirect('login')
