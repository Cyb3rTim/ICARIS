from django.urls import path

from . import views

app_name = "ato"

urlpatterns = [
    path("systems/", views.system_list, name="system_list"),
    path("systems/new/", views.system_create, name="system_create"),
    path("systems/<int:pk>/", views.system_detail, name="system_detail"),
    path("systems/<int:pk>/edit/", views.system_update, name="system_update"),
    path("systems/<int:pk>/apply-baseline/", views.system_apply_baseline, name="system_apply_baseline"),
    path("systems/<int:system_pk>/packages/new/", views.package_create, name="package_create"),
    path("implementations/<int:pk>/", views.implementation_update, name="implementation_update"),
    path("packages/<int:pk>/", views.package_detail, name="package_detail"),
    path("packages/<int:pk>/edit/", views.package_update, name="package_update"),
    path("documents/<int:pk>/", views.document_update, name="document_update"),
    path("controls/", views.control_list, name="control_list"),
    path("controls/<str:control_id>/", views.control_detail, name="control_detail"),
]
