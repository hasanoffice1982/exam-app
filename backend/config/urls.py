from django.contrib import admin
from django.urls import include, path

from apps.proctoring.home import HomeView

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("admin/", admin.site.urls),
    path("api/", include("apps.proctoring.urls")),
    path("teacher/", include("apps.proctoring.teacher_urls")),
    # Screenshots are deliberately NOT served from /media/: teachers get them via access-checked views.
]
