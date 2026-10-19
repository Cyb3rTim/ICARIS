"""Root URL configuration for ICARIS."""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="registration/login.html", redirect_authenticated_user=True),
        name="login",
    ),
    path("", include("grc_dashboard.urls")),
]

# Uploaded files are deliberately NOT served from /media/. Every download goes
# through an authenticated view (see grc_dashboard.views._serve_protected_file).
