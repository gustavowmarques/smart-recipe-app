# config/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),                    # home, dashboard, pantry, AI/Web recipes
    path("accounts/", include("django.contrib.auth.urls")),  # login/logout/password
    path("accounts/", include("accounts.urls")),             # register
]
