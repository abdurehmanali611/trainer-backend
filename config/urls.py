from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/", include("apps.fitness.urls")),
    path("api/platform/", include("apps.platform_billing.urls_trainer")),
    path("internal/admin/", include("apps.platform_billing.urls_admin")),
    path("internal/", include("apps.internal.urls")),
]
