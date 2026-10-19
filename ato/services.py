"""Business operations for the ATO module (kept out of views for testability)."""
from django.db import transaction

from .catalog import CatalogData
from .models import (
    AuthorizationPackage,
    ControlFamily,
    ControlImplementation,
    InformationSystem,
    PackageDocument,
    SecurityControl,
    systems_expiring,
)


@transaction.atomic
def import_catalog(data: CatalogData) -> dict:
    """Create or update control families and controls from parsed catalog data."""
    families = {}
    for code, title in data.families.items():
        families[code], _ = ControlFamily.objects.update_or_create(code=code, defaults={"title": title})

    created = updated = 0
    by_id = {}
    for record in data.controls:
        obj, was_created = SecurityControl.objects.update_or_create(
            control_id=record.control_id,
            defaults={
                "label": record.label,
                "title": record.title,
                "family": families[record.family],
                "sort_key": record.sort_key,
                "statement": record.statement,
                "withdrawn": record.withdrawn,
                "in_low": "low" in record.baselines,
                "in_moderate": "moderate" in record.baselines,
                "in_high": "high" in record.baselines,
                "catalog_version": data.version,
            },
        )
        by_id[record.control_id] = obj
        created += was_created
        updated += not was_created

    # Second pass so parents exist before enhancements reference them.
    for record in data.controls:
        if record.parent_id:
            SecurityControl.objects.filter(pk=by_id[record.control_id].pk).update(parent=by_id[record.parent_id])

    return {"families": len(families), "created": created, "updated": updated}


@transaction.atomic
def apply_baseline(system: InformationSystem) -> int:
    """Add every control in the system's FIPS 199 baseline that it does not track yet.

    Returns the number of control implementations created. Existing entries
    (and any tailoring already done) are left untouched.
    """
    existing = set(system.implementations.values_list("control_id", flat=True))
    controls = SecurityControl.baseline_queryset(system.categorization).exclude(pk__in=existing)
    rows = [ControlImplementation(system=system, control=control) for control in controls]
    ControlImplementation.objects.bulk_create(rows)
    return len(rows)


@transaction.atomic
def create_package(system: InformationSystem, name: str, **fields) -> AuthorizationPackage:
    """Open a new authorization package with the standard document checklist."""
    package = AuthorizationPackage.objects.create(system=system, name=name, **fields)
    PackageDocument.objects.bulk_create(
        PackageDocument(package=package, doc_type=doc_type) for doc_type in PackageDocument.DEFAULT_REQUIRED
    )
    return package


def ato_summary() -> dict:
    """Portfolio-level ATO figures for the main dashboard."""
    systems = list(InformationSystem.objects.prefetch_related("packages"))
    authorized = [s for s in systems if s.current_authorization and s.current_authorization.is_authorized]
    return {
        "systems": len(systems),
        "authorized": len(authorized),
        "expiring": systems_expiring(within_days=180),
    }
