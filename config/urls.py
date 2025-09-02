from django.contrib import admin
from django.urls import path, include
from core.views import home, dashboard

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", home, name="home"),
    path("", include("core.urls")), 
    path("accounts/", include("django.contrib.auth.urls")),  # login/logout
    path("accounts/", include("accounts.urls")),             # register
]
