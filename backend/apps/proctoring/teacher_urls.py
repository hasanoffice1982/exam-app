from django.urls import path

from . import teacher_views as v

urlpatterns = [
    path("", v.ExamListView.as_view(), name="teacher-exams"),
    path("exams/<slug:exam_id>/", v.MonitorView.as_view(), name="teacher-monitor"),
    path("exams/<slug:exam_id>/live.json", v.LiveJsonView.as_view(), name="teacher-live"),
    path("exams/<slug:exam_id>/students/<str:roll>/", v.StudentTimelineView.as_view(), name="teacher-timeline"),
    path("exams/<slug:exam_id>/screenshots/<int:pk>/", v.ScreenshotView.as_view(), name="teacher-screenshot"),
    path("exams/<slug:exam_id>/passwords/", v.BatchPasswordsView.as_view(), name="teacher-passwords"),
    path("exams/<slug:exam_id>/marks/", v.MarksView.as_view(), name="teacher-marks"),
    path("exams/<slug:exam_id>/summary.csv", v.CsvExportView.as_view(kind="summary"), name="teacher-csv-summary"),
    path("exams/<slug:exam_id>/events.csv", v.CsvExportView.as_view(kind="events"), name="teacher-csv-events"),
    path("exams/<slug:exam_id>/attempts/<int:pk>/force-end/", v.AttemptActionView.as_view(action="force_end"), name="teacher-force-end"),
    path("exams/<slug:exam_id>/attempts/<int:pk>/extra-time/", v.ExtraTimeView.as_view(), name="teacher-extra-time"),
    path("exams/<slug:exam_id>/attempts/<int:pk>/reset/", v.AttemptActionView.as_view(action="reset"), name="teacher-reset"),
]
