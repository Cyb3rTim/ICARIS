# grc_dashboard/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth import logout
from django.http import FileResponse, Http404, JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.db.models import Count, Q, Avg
from django.utils import timezone
from django.contrib import messages
from datetime import timedelta

from .models import Risk, ComplianceControl, Audit, Issue, Department, Artifact
from .forms import RiskForm, ComplianceControlForm, AuditForm, IssueForm
from . import audit_log

@login_required
def dashboard(request):
    """Main GRC dashboard with key metrics and visualizations"""
    
    # Risk metrics
    total_risks = Risk.objects.count()
    critical_risks = Risk.objects.filter(severity='critical', status__in=['open', 'in_progress']).count()
    open_risks = Risk.objects.filter(status='open').count()
    
    # Compliance metrics
    total_controls = ComplianceControl.objects.count()
    compliant_controls = ComplianceControl.objects.filter(status='compliant').count()
    non_compliant_controls = ComplianceControl.objects.filter(status='non_compliant').count()
    compliance_rate = (compliant_controls / total_controls * 100) if total_controls > 0 else 0
    
    # Audit metrics
    total_audits = Audit.objects.count()
    upcoming_audits = Audit.objects.filter(
        status='planned',
        start_date__lte=timezone.now().date() + timedelta(days=30)
    ).count()
    in_progress_audits = Audit.objects.filter(status='in_progress').count()
    
    # Issue metrics
    total_issues = Issue.objects.count()
    open_issues = Issue.objects.filter(status__in=['open', 'in_progress']).count()
    overdue_issues = Issue.objects.filter(
        status__in=['open', 'in_progress'],
        due_date__lt=timezone.now().date()
    ).count()
    
    # Risk by severity
    risks_by_severity = Risk.objects.values('severity').annotate(count=Count('id'))
    
    # Compliance by status
    compliance_by_status = ComplianceControl.objects.values('status').annotate(count=Count('id'))
    
    # Recent activities
    recent_risks = Risk.objects.select_related('department', 'owner').order_by('-created_at')[:5]
    recent_audits = Audit.objects.select_related('department', 'auditor').order_by('-created_at')[:5]
    recent_issues = Issue.objects.select_related('department', 'assigned_to').order_by('-created_at')[:5]
    
    context = {
        'total_risks': total_risks,
        'critical_risks': critical_risks,
        'open_risks': open_risks,
        'total_controls': total_controls,
        'compliance_rate': round(compliance_rate, 1),
        'non_compliant_controls': non_compliant_controls,
        'total_audits': total_audits,
        'upcoming_audits': upcoming_audits,
        'in_progress_audits': in_progress_audits,
        'total_issues': total_issues,
        'open_issues': open_issues,
        'overdue_issues': overdue_issues,
        'risks_by_severity': risks_by_severity,
        'compliance_by_status': compliance_by_status,
        'recent_risks': recent_risks,
        'recent_audits': recent_audits,
        'recent_issues': recent_issues,
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
    """PO&AM list with filters and live status counts."""
    all_issues = Issue.objects.select_related('department', 'assigned_to')
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
            messages.success(request, 'PO&AM created.')
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
            messages.success(request, 'PO&AM updated.')
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
