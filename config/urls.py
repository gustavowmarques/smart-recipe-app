from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),

    # Core app (namespaced)
    path("", include(("core.urls", "core"), namespace="core")),

    # Django auth (provides 'login', 'logout', password URLs)
    path("accounts/", include("django.contrib.auth.urls")),

    path("accounts/", include(("accounts.urls", "accounts"), namespace="accounts")),



]
