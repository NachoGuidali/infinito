from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),

    # Auth (login, logout, password reset, etc.)
    path("", include("django.contrib.auth.urls")),

    # App LMS
    path("", include("lms.urls")),
]
