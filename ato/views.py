from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from grc_dashboard import audit_log

from . import services
from .forms import AuthorizationPackageForm, ControlImplementationForm, InformationSystemForm, PackageDocumentForm
from .models import (
    AuthorizationPackage,
    ControlFamily,
    ControlImplementation,
    InformationSystem,
    PackageDocument,
    SecurityControl,
    systems_expiring,
)

OPEN_POAM_STATUSES = ["open", "in_progress"]


# ---------------------------------------------------------------------------
# Systems
# ---------------------------------------------------------------------------
@login_required
def system_list(request):
    systems = InformationSystem.objects.select_related("isso").prefetch_related("packages").annotate(
        open_poams=Count("poams", filter=Q(poams__status__in=OPEN_POAM_STATUSES), distinct=True)
    )
    rows = [{"system": s, "auth": s.current_authorization, "summary": s.implementation_summary()} for s in systems]
    return render(request, "ato/system_list.html", {
        "rows": rows,
        "expiring": systems_expiring(within_days=180),
        "catalog_loaded": SecurityControl.objects.exists(),
    })


@login_required
def system_detail(request, pk):
    system = get_object_or_404(InformationSystem.objects.select_related("system_owner", "isso"), pk=pk)
    implementations = system.implementations.select_related("control", "control__family")

    family_filter = request.GET.get("family", "")
    status_filter = request.GET.get("status", "")
    query = request.GET.get("q", "").strip()
    filtered = implementations
    if family_filter:
        filtered = filtered.filter(control__family__code=family_filter)
    if status_filter:
        filtered = filtered.filter(status=status_filter)
    if query:
        filtered = filtered.filter(Q(control__label__icontains=query) | Q(control__title__icontains=query))

    coverage = (
        implementations.values("control__family__code", "control__family__title")
        .annotate(
            total=Count("id"),
            implemented=Count("id", filter=Q(status=ControlImplementation.Status.IMPLEMENTED)),
            not_applicable=Count("id", filter=Q(status=ControlImplementation.Status.NOT_APPLICABLE)),
        )
        .order_by("control__family__code")
    )
    for row in coverage:
        applicable = row["total"] - row["not_applicable"]
        row["percent"] = round(100 * row["implemented"] / applicable) if applicable else 100

    page = Paginator(filtered, 25).get_page(request.GET.get("page"))
    return render(request, "ato/system_detail.html", {
        "system": system,
        "summary": system.implementation_summary(),
        "auth": system.current_authorization,
        "packages": system.packages.all(),
        "coverage": coverage,
        "page": page,
        "families": ControlFamily.objects.filter(controls__implementations__system=system).distinct(),
        "statuses": ControlImplementation.Status.choices,
        "family_filter": family_filter,
        "status_filter": status_filter,
        "query": query,
        "poams": system.poams.filter(status__in=OPEN_POAM_STATUSES).select_related("control")[:10],
        "baseline_size": SecurityControl.baseline_queryset(system.categorization).count(),
    })


@login_required
@permission_required("ato.add_informationsystem", raise_exception=True)
def system_create(request):
    form = InformationSystemForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        system = form.save()
        audit_log.record(request, "create", system)
        messages.success(request, f"{system.acronym} registered. Apply its {system.get_categorization_display()} baseline next.")
        return redirect("ato:system_detail", pk=system.pk)
    return render(request, "ato/form.html", {"form": form, "title": "Register System", "cancel_url": reverse("ato:system_list")})


@login_required
@permission_required("ato.change_informationsystem", raise_exception=True)
def system_update(request, pk):
    system = get_object_or_404(InformationSystem, pk=pk)
    form = InformationSystemForm(request.POST or None, instance=system)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit_log.record(request, "update", system)
        messages.success(request, "System updated.")
        return redirect("ato:system_detail", pk=system.pk)
    return render(request, "ato/form.html", {
        "form": form, "title": f"Edit {system.acronym}", "cancel_url": system.get_absolute_url(),
    })


@login_required
@require_POST
@permission_required("ato.add_controlimplementation", raise_exception=True)
def system_apply_baseline(request, pk):
    system = get_object_or_404(InformationSystem, pk=pk)
    if not SecurityControl.objects.exists():
        messages.error(request, "Load the NIST control catalog first (manage.py import_oscal_catalog).")
        return redirect("ato:system_detail", pk=pk)
    added = services.apply_baseline(system)
    audit_log.record(request, "apply_baseline", system)
    if added:
        messages.success(request, f"Added {added} controls from the {system.get_categorization_display()} baseline.")
    else:
        messages.info(request, "Every baseline control is already tracked for this system.")
    return redirect("ato:system_detail", pk=pk)


# ---------------------------------------------------------------------------
# Control implementations
# ---------------------------------------------------------------------------
@login_required
@permission_required("ato.change_controlimplementation", raise_exception=True)
def implementation_update(request, pk):
    impl = get_object_or_404(ControlImplementation.objects.select_related("system", "control"), pk=pk)
    form = ControlImplementationForm(request.POST or None, instance=impl)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit_log.record(request, "update", impl)
        messages.success(request, f"{impl.control.label} updated.")
        return redirect(f"{impl.system.get_absolute_url()}?family={impl.control.family.code}")
    return render(request, "ato/implementation_form.html", {"form": form, "impl": impl})


# ---------------------------------------------------------------------------
# Authorization packages
# ---------------------------------------------------------------------------
@login_required
@permission_required("ato.add_authorizationpackage", raise_exception=True)
def package_create(request, system_pk):
    system = get_object_or_404(InformationSystem, pk=system_pk)
    form = AuthorizationPackageForm(request.POST or None, initial={"name": f"{system.acronym} authorization"})
    if request.method == "POST" and form.is_valid():
        fields = {k: v for k, v in form.cleaned_data.items() if k != "name"}
        package = services.create_package(system, form.cleaned_data["name"], **fields)
        audit_log.record(request, "create", package)
        messages.success(request, "Package opened with the standard document checklist.")
        return redirect("ato:package_detail", pk=package.pk)
    return render(request, "ato/form.html", {
        "form": form, "title": f"New authorization package for {system.acronym}", "cancel_url": system.get_absolute_url(),
    })


@login_required
def package_detail(request, pk):
    package = get_object_or_404(AuthorizationPackage.objects.select_related("system"), pk=pk)
    return render(request, "ato/package_detail.html", {
        "package": package,
        "documents": package.documents.select_related("artifact"),
        "readiness": package.readiness(),
        "summary": package.system.implementation_summary(),
        "open_poams": package.system.poams.filter(status__in=OPEN_POAM_STATUSES).count(),
    })


@login_required
@permission_required("ato.change_authorizationpackage", raise_exception=True)
def package_update(request, pk):
    package = get_object_or_404(AuthorizationPackage.objects.select_related("system"), pk=pk)
    form = AuthorizationPackageForm(request.POST or None, instance=package)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit_log.record(request, "update", package)
        messages.success(request, "Package updated.")
        return redirect("ato:package_detail", pk=package.pk)
    return render(request, "ato/form.html", {
        "form": form, "title": f"Update {package}", "cancel_url": package.get_absolute_url(),
    })


@login_required
@permission_required("ato.change_packagedocument", raise_exception=True)
def document_update(request, pk):
    document = get_object_or_404(PackageDocument.objects.select_related("package"), pk=pk)
    form = PackageDocumentForm(request.POST or None, instance=document)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit_log.record(request, "update", document)
        messages.success(request, f"{document.get_doc_type_display()} updated.")
        return redirect("ato:package_detail", pk=document.package_id)
    return render(request, "ato/form.html", {
        "form": form, "title": document.get_doc_type_display(), "cancel_url": document.package.get_absolute_url(),
    })


# ---------------------------------------------------------------------------
# Control catalog
# ---------------------------------------------------------------------------
@login_required
def control_list(request):
    controls = SecurityControl.objects.select_related("family").filter(withdrawn=False)
    family = request.GET.get("family", "")
    baseline = request.GET.get("baseline", "")
    query = request.GET.get("q", "").strip()
    if family:
        controls = controls.filter(family__code=family)
    if baseline in ("low", "moderate", "high"):
        controls = controls.filter(**{f"in_{baseline}": True})
    if query:
        controls = controls.filter(Q(label__icontains=query) | Q(title__icontains=query) | Q(statement__icontains=query))
    page = Paginator(controls, 50).get_page(request.GET.get("page"))
    return render(request, "ato/control_list.html", {
        "page": page, "families": ControlFamily.objects.all(),
        "family": family, "baseline": baseline, "query": query,
        "total": controls.count(),
        "version": SecurityControl.objects.values_list("catalog_version", flat=True).first(),
    })


@login_required
def control_detail(request, control_id):
    control = get_object_or_404(SecurityControl.objects.select_related("family", "parent"), control_id=control_id)
    return render(request, "ato/control_detail.html", {
        "control": control,
        "enhancements": control.enhancements.filter(withdrawn=False),
        "implementations": control.implementations.select_related("system"),
    })
