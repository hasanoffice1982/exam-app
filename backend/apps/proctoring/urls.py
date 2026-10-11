from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("consent", views.ConsentViewSet, basename="consent")
router.register("events", views.ProctorEventViewSet, basename="event")
router.register("screenshots", views.ProctorScreenshotViewSet, basename="screenshot")

urlpatterns = [
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("auth/change-password/", views.ChangePasswordView.as_view(), name="change-password"),
    path("auth/logout/", views.LogoutView.as_view(), name="logout"),
    path("heartbeat/", views.HeartbeatView.as_view(), name="heartbeat"),
    path("auth/activate/", views.ActivateView.as_view(), name="activate"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("exams/", views.ExamListView.as_view(), name="exam-list"),
    path("exams/<slug:exam_id>/advance/", views.ExamAdvanceView.as_view(), name="exam-advance"),
    path("exams/<slug:exam_id>/start/", views.ExamStartView.as_view(), name="exam-start"),
    path("config/<slug:exam_id>/", views.ExamConfigView.as_view(), name="exam-config"),
    path("", include(router.urls)),
]
