from django import forms

from .models import AuthorizationPackage, ControlImplementation, InformationSystem, PackageDocument


class StyledModelForm(forms.ModelForm):
    """Apply the dashboard's form-control styling to every widget."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = "form-check-input" if isinstance(field.widget, forms.CheckboxInput) else "form-control"
            field.widget.attrs.setdefault("class", css)


class DateInput(forms.DateInput):
    input_type = "date"


class InformationSystemForm(StyledModelForm):
    class Meta:
        model = InformationSystem
        fields = [
            "name", "acronym", "description", "environment",
            "confidentiality", "integrity", "availability",
            "rmf_step", "system_owner", "isso", "authorizing_official",
        ]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}
        help_texts = {
            "confidentiality": "FIPS 199 impact if confidentiality is lost",
            "integrity": "FIPS 199 impact if integrity is lost",
            "availability": "FIPS 199 impact if availability is lost",
        }


class ControlImplementationForm(StyledModelForm):
    class Meta:
        model = ControlImplementation
        fields = [
            "status", "origination", "inherited_from", "responsible_role",
            "implementation_statement", "assessment_result", "last_assessed",
        ]
        widgets = {
            "implementation_statement": forms.Textarea(attrs={"rows": 6}),
            "last_assessed": DateInput(),
        }


class AuthorizationPackageForm(StyledModelForm):
    class Meta:
        model = AuthorizationPackage
        fields = [
            "name", "status", "target_decision_date", "decision", "decision_date",
            "expiration_date", "ongoing_authorization", "conditions",
        ]
        widgets = {
            "target_decision_date": DateInput(),
            "decision_date": DateInput(),
            "expiration_date": DateInput(),
            "conditions": forms.Textarea(attrs={"rows": 3}),
        }


class PackageDocumentForm(StyledModelForm):
    class Meta:
        model = PackageDocument
        fields = ["status", "artifact", "notes"]
