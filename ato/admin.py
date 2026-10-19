from django.contrib import admin

from .models import (
    AuthorizationPackage,
    ControlFamily,
    ControlImplementation,
    InformationSystem,
    PackageDocument,
    SecurityControl,
)


@admin.register(ControlFamily)
class ControlFamilyAdmin(admin.ModelAdmin):
    list_display = ["code", "title"]


@admin.register(SecurityControl)
class SecurityControlAdmin(admin.ModelAdmin):
    list_display = ["label", "title", "family", "in_low", "in_moderate", "in_high", "withdrawn"]
    list_filter = ["family", "in_low", "in_moderate", "in_high", "withdrawn"]
    search_fields = ["control_id", "label", "title", "statement"]
    readonly_fields = [f.name for f in SecurityControl._meta.fields]


class ControlImplementationInline(admin.TabularInline):
    model = ControlImplementation
    extra = 0
    fields = ["control", "status", "origination", "assessment_result"]
    raw_id_fields = ["control"]
    show_change_link = True


@admin.register(InformationSystem)
class InformationSystemAdmin(admin.ModelAdmin):
    list_display = ["acronym", "name", "categorization", "rmf_step", "isso"]
    list_filter = ["rmf_step", "environment"]
    search_fields = ["acronym", "name"]


@admin.register(ControlImplementation)
class ControlImplementationAdmin(admin.ModelAdmin):
    list_display = ["system", "control", "status", "origination", "assessment_result", "last_assessed"]
    list_filter = ["system", "status", "origination", "assessment_result", "control__family"]
    search_fields = ["control__label", "control__title", "implementation_statement"]
    raw_id_fields = ["control"]


class PackageDocumentInline(admin.TabularInline):
    model = PackageDocument
    extra = 0
    raw_id_fields = ["artifact"]


@admin.register(AuthorizationPackage)
class AuthorizationPackageAdmin(admin.ModelAdmin):
    list_display = ["system", "name", "status", "decision", "decision_date", "expiration_date"]
    list_filter = ["status", "decision"]
    inlines = [PackageDocumentInline]
