# grc_dashboard/admin.py
from django.contrib import admin

from .models import Audit, ComplianceControl, ComplianceFramework, Department, Issue, Risk


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name']


@admin.register(Risk)
class RiskAdmin(admin.ModelAdmin):
    list_display = ['title', 'department', 'severity', 'status', 'risk_score', 'owner', 'created_at']
    list_filter = ['severity', 'status', 'department', 'created_at']
    search_fields = ['title', 'description']
    date_hierarchy = 'created_at'
    readonly_fields = ['risk_score', 'created_at', 'updated_at']

    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'description', 'department', 'owner')
        }),
        ('Risk Assessment', {
            'fields': ('severity', 'likelihood', 'impact', 'risk_score', 'status')
        }),
        ('Mitigation', {
            'fields': ('mitigation_plan', 'identified_date', 'target_closure_date')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ComplianceFramework)
class ComplianceFrameworkAdmin(admin.ModelAdmin):
    list_display = ['name', 'version', 'created_at']
    search_fields = ['name', 'description']


@admin.register(ComplianceControl)
class ComplianceControlAdmin(admin.ModelAdmin):
    list_display = ['control_id', 'title', 'framework', 'department', 'status', 'owner', 'last_assessment_date']
    list_filter = ['status', 'framework', 'department', 'last_assessment_date']
    search_fields = ['control_id', 'title', 'description']
    date_hierarchy = 'last_assessment_date'

    fieldsets = (
        ('Control Information', {
            'fields': ('framework', 'control_id', 'title', 'description')
        }),
        ('Assignment', {
            'fields': ('department', 'owner', 'status')
        }),
        ('Assessment', {
            'fields': ('evidence', 'last_assessment_date', 'next_assessment_date')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Audit)
class AuditAdmin(admin.ModelAdmin):
    list_display = ['title', 'audit_type', 'department', 'status', 'auditor', 'start_date', 'end_date']
    list_filter = ['audit_type', 'status', 'department', 'start_date']
    search_fields = ['title', 'scope', 'findings']
    date_hierarchy = 'start_date'

    fieldsets = (
        ('Audit Information', {
            'fields': ('title', 'audit_type', 'department', 'auditor', 'status')
        }),
        ('Scope and Timeline', {
            'fields': ('scope', 'start_date', 'end_date')
        }),
        ('Results', {
            'fields': ('findings', 'recommendations')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = ['title', 'priority', 'status', 'department', 'assigned_to', 'due_date', 'created_at']
    list_filter = ['priority', 'status', 'department', 'due_date', 'created_at']
    search_fields = ['title', 'description']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Issue Information', {
            'fields': ('title', 'description', 'priority', 'status')
        }),
        ('Assignment', {
            'fields': ('department', 'assigned_to', 'due_date')
        }),
        ('Related Items', {
            'fields': ('related_risk', 'related_audit')
        }),
        ('Resolution', {
            'fields': ('resolution_notes',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
