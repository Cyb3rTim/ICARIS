# grc_dashboard/forms.py
from django import forms

from .models import Artifact, Audit, ComplianceControl, Issue, Risk
from .validators import ALLOWED_EXTENSIONS

ACCEPT_ATTR = ",".join(f".{ext}" for ext in ALLOWED_EXTENSIONS)

class RiskForm(forms.ModelForm):
    class Meta:
        model = Risk
        fields = [
            'title', 'description', 'department', 'owner', 'severity',
            'likelihood', 'impact', 'status', 'compliance_percentage',
            'mitigation_plan', 'identified_date', 'target_closure_date',
            'evidence_file',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'department': forms.Select(attrs={'class': 'form-control'}),
            'severity': forms.Select(attrs={'class': 'form-control'}),
            'likelihood': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 5}),
            'impact': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 5}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'mitigation_plan': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'identified_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'target_closure_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'owner': forms.Select(attrs={'class': 'form-control'}),
            'compliance_percentage': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 100}),
            'evidence_file': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': ACCEPT_ATTR}),
        }


class ComplianceControlForm(forms.ModelForm):
    class Meta:
        model = ComplianceControl
        fields = [
            'framework', 'control_id', 'title', 'description',
            'department', 'status', 'evidence',
            'last_assessment_date', 'next_assessment_date'
        ]
        widgets = {
            'framework': forms.Select(attrs={'class': 'form-control'}),
            'control_id': forms.TextInput(attrs={'class': 'form-control'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'department': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'evidence': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'last_assessment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'next_assessment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }


class AuditForm(forms.ModelForm):
    class Meta:
        model = Audit
        fields = [
            'title', 'audit_type', 'department', 'status',
            'scope', 'start_date', 'end_date',
            'findings', 'recommendations'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'audit_type': forms.Select(attrs={'class': 'form-control'}),
            'department': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'scope': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'findings': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'recommendations': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }


class IssueForm(forms.ModelForm):
    class Meta:
        model = Issue
        fields = [
            'title', 'description', 'priority', 'status',
            'department', 'assigned_to', 'related_risk',
            'related_audit', 'due_date', 'resolution_notes'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'priority': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'department': forms.Select(attrs={'class': 'form-control'}),
            'assigned_to': forms.Select(attrs={'class': 'form-control'}),
            'related_risk': forms.Select(attrs={'class': 'form-control'}),
            'related_audit': forms.Select(attrs={'class': 'form-control'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'resolution_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class ArtifactForm(forms.ModelForm):
    class Meta:
        model = Artifact
        fields = ['title', 'description', 'category', 'department', 'file']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'department': forms.Select(attrs={'class': 'form-control'}),
            'file': forms.FileInput(attrs={'class': 'form-control', 'accept': ACCEPT_ATTR}),
        }
