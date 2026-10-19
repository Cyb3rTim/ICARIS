import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'grc_project.settings')
django.setup()

from datetime import date, timedelta

from django.contrib.auth.models import User

from grc_dashboard.models import Audit, ComplianceControl, ComplianceFramework, Department, Issue, Risk

print("Creating sample data...")

# Get or create admin user
try:
    admin = User.objects.get(username='admin')
except User.DoesNotExist:
    admin = User.objects.first()
    if not admin:
        print("No users found. Please create a superuser first!")
        exit()

# Create departments
print("Creating departments...")
it_dept, _ = Department.objects.get_or_create(
    name="IT Security",
    defaults={'description': "Information Technology and Security"}
)
hr_dept, _ = Department.objects.get_or_create(
    name="Human Resources",
    defaults={'description': "Human Resources Department"}
)
finance_dept, _ = Department.objects.get_or_create(
    name="Finance",
    defaults={'description': "Finance and Accounting"}
)
ops_dept, _ = Department.objects.get_or_create(
    name="Operations",
    defaults={'description': "Business Operations"}
)

# Create risks
print("Creating risks...")
Risk.objects.get_or_create(
    title="Data Breach Risk",
    defaults={
        'description': "Potential unauthorized access to sensitive customer data through insecure API endpoints",
        'department': it_dept,
        'severity': 'critical',
        'likelihood': 4,
        'impact': 5,
        'status': 'open',
        'owner': admin,
        'mitigation_plan': "Implement API authentication, conduct security audit, enable monitoring",
        'identified_date': date.today(),
        'target_closure_date': date.today() + timedelta(days=30)
    }
)

Risk.objects.get_or_create(
    title="Regulatory Compliance Gap - GDPR",
    defaults={
        'description': "Non-compliance with GDPR data retention and privacy requirements",
        'department': it_dept,
        'severity': 'high',
        'likelihood': 3,
        'impact': 4,
        'status': 'in_progress',
        'owner': admin,
        'mitigation_plan': "Review data retention policies, implement automated deletion, train staff",
        'identified_date': date.today() - timedelta(days=15),
        'target_closure_date': date.today() + timedelta(days=45)
    }
)

Risk.objects.get_or_create(
    title="Insider Threat - Privileged Access",
    defaults={
        'description': "Risk of data exfiltration by users with elevated privileges",
        'department': it_dept,
        'severity': 'high',
        'likelihood': 2,
        'impact': 5,
        'status': 'open',
        'owner': admin,
        'mitigation_plan': "Implement least privilege, enable access logging, conduct background checks",
        'identified_date': date.today() - timedelta(days=5),
        'target_closure_date': date.today() + timedelta(days=60)
    }
)

Risk.objects.get_or_create(
    title="Third-Party Vendor Risk",
    defaults={
        'description': "Security vulnerabilities in third-party vendor systems",
        'department': ops_dept,
        'severity': 'medium',
        'likelihood': 3,
        'impact': 3,
        'status': 'in_progress',
        'owner': admin,
        'mitigation_plan': "Conduct vendor security assessments, require SOC 2 compliance",
        'identified_date': date.today() - timedelta(days=20),
        'target_closure_date': date.today() + timedelta(days=90)
    }
)

Risk.objects.get_or_create(
    title="Employee Security Awareness Gap",
    defaults={
        'description': "Staff lack awareness of phishing and social engineering attacks",
        'department': hr_dept,
        'severity': 'medium',
        'likelihood': 4,
        'impact': 2,
        'status': 'open',
        'owner': admin,
        'mitigation_plan': "Deploy security awareness training, conduct phishing simulations",
        'identified_date': date.today() - timedelta(days=10),
        'target_closure_date': date.today() + timedelta(days=30)
    }
)

Risk.objects.get_or_create(
    title="Business Continuity Planning",
    defaults={
        'description': "Inadequate disaster recovery and business continuity plans",
        'department': ops_dept,
        'severity': 'low',
        'likelihood': 2,
        'impact': 3,
        'status': 'mitigated',
        'owner': admin,
        'mitigation_plan': "Develop and test BCP, establish backup procedures",
        'identified_date': date.today() - timedelta(days=60),
        'target_closure_date': date.today() - timedelta(days=5)
    }
)

# Create compliance frameworks
print("Creating compliance frameworks...")
gdpr, _ = ComplianceFramework.objects.get_or_create(
    name="GDPR",
    defaults={
        'description': "General Data Protection Regulation - EU data protection and privacy",
        'version': "2016/679"
    }
)

sox, _ = ComplianceFramework.objects.get_or_create(
    name="SOX",
    defaults={
        'description': "Sarbanes-Oxley Act - Financial reporting and internal controls",
        'version': "2002"
    }
)

nist, _ = ComplianceFramework.objects.get_or_create(
    name="NIST CSF",
    defaults={
        'description': "NIST Cybersecurity Framework",
        'version': "2.0"
    }
)

# Create compliance controls
print("Creating compliance controls...")
ComplianceControl.objects.get_or_create(
    framework=gdpr,
    control_id="GDPR-7.1",
    defaults={
        'title': "Right to Access",
        'description': "Individuals have the right to access their personal data and understand how it is processed",
        'department': it_dept,
        'status': 'compliant',
        'owner': admin,
        'evidence': "Data subject access request procedure documented and tested",
        'last_assessment_date': date.today() - timedelta(days=30),
        'next_assessment_date': date.today() + timedelta(days=90)
    }
)

ComplianceControl.objects.get_or_create(
    framework=sox,
    control_id="SOX-404",
    defaults={
        'title': "Internal Control Assessment",
        'description': "Management must assess and report on the effectiveness of internal controls",
        'department': finance_dept,
        'status': 'in_progress',
        'owner': admin,
        'evidence': "Annual assessment in progress, documentation being compiled",
        'last_assessment_date': date.today() - timedelta(days=180),
        'next_assessment_date': date.today() + timedelta(days=45)
    }
)

ComplianceControl.objects.get_or_create(
    framework=nist,
    control_id="NIST-ID.AM-1",
    defaults={
        'title': "Asset Management",
        'description': "Physical devices and systems are inventoried and managed",
        'department': it_dept,
        'status': 'compliant',
        'owner': admin,
        'evidence': "Asset inventory maintained in CMDB, quarterly reviews conducted",
        'last_assessment_date': date.today() - timedelta(days=15),
        'next_assessment_date': date.today() + timedelta(days=75)
    }
)

ComplianceControl.objects.get_or_create(
    framework=nist,
    control_id="NIST-PR.AC-1",
    defaults={
        'title': "Access Control",
        'description': "Identities and credentials are issued, managed, verified, revoked for authorized devices and users",
        'department': it_dept,
        'status': 'non_compliant',
        'owner': admin,
        'evidence': "Gap identified: No automated deprovisioning for terminated employees",
        'last_assessment_date': date.today() - timedelta(days=10),
        'next_assessment_date': date.today() + timedelta(days=30)
    }
)

# Create audits
print("Creating audits...")
Audit.objects.get_or_create(
    title="Annual SOC 2 Type II Audit",
    defaults={
        'audit_type': 'external',
        'department': it_dept,
        'status': 'in_progress',
        'auditor': admin,
        'scope': "Review of security controls for SOC 2 Type II compliance",
        'start_date': date.today() - timedelta(days=30),
        'end_date': date.today() + timedelta(days=30),
        'findings': "Initial findings indicate strong access controls, minor gaps in change management",
        'recommendations': "Implement formal change approval board, enhance documentation"
    }
)

Audit.objects.get_or_create(
    title="Q4 Internal Security Audit",
    defaults={
        'audit_type': 'internal',
        'department': it_dept,
        'status': 'completed',
        'auditor': admin,
        'scope': "Internal review of security policies and procedures",
        'start_date': date.today() - timedelta(days=90),
        'end_date': date.today() - timedelta(days=60),
        'findings': "All security policies up to date, staff training completed",
        'recommendations': "Continue quarterly training, update incident response plan"
    }
)

# Create issues
print("Creating issues...")
Issue.objects.get_or_create(
    title="Activate Windows Defender on all endpoints",
    defaults={
        'description': "Ensure all workstations have Windows Defender enabled and updated",
        'priority': 'high',
        'status': 'in_progress',
        'department': it_dept,
        'assigned_to': admin,
        'due_date': date.today() + timedelta(days=14),
        'resolution_notes': "85% complete, 15 remaining endpoints"
    }
)

Issue.objects.get_or_create(
    title="Update firewall ruleset for new application",
    defaults={
        'description': "Configure firewall rules to allow traffic for newly deployed CRM system",
        'priority': 'critical',
        'status': 'open',
        'department': it_dept,
        'assigned_to': admin,
        'due_date': date.today() + timedelta(days=7),
        'resolution_notes': ""
    }
)

Issue.objects.get_or_create(
    title="Complete annual security awareness training",
    defaults={
        'description': "All employees must complete mandatory security awareness training",
        'priority': 'medium',
        'status': 'resolved',
        'department': hr_dept,
        'assigned_to': admin,
        'due_date': date.today() - timedelta(days=5),
        'resolution_notes': "100% completion achieved, certificates issued"
    }
)

print("Sample data created successfully!")
print("\nYou can now:")
print("1. Visit http://127.0.0.1:8000/ to see the dashboard")
print("2. Go to http://127.0.0.1:8000/admin/ to manage data")
print("3. Explore the Risk Register at http://127.0.0.1:8000/risks/")
