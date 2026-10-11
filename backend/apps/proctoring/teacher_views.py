import json
import mimetypes

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import FormView, TemplateView

from . import dashboard, marking, services
from .forms import MarksUploadForm
from .models import Student
from .sheets import password_sheet_response
from .models import ExamAttempt, ProctorScreenshot

T = "proctoring/teacher/"


class TeacherMixin(LoginRequiredMixin):
    """Staff only (login via /admin/login/). Every lookup is scoped to the teacher's own exams."""

    login_url = "/admin/login/"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.is_staff:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_exam(self):
        return get_object_or_404(dashboard.scoped_exams(self.request.user), exam_id=self.kwargs["exam_id"])


class ExamListView(TeacherMixin, TemplateView):
    template_name = T + "exam_list.html"

    def get_context_data(self, **kwargs):
        exams = dashboard.scoped_exams(self.request.user).annotate(
            total=Count("attempts", distinct=True),
            active=Count("attempts", filter=Q(attempts__status=ExamAttempt.Status.IN_PROGRESS), distinct=True),
        )
        return {**super().get_context_data(**kwargs), "exams": exams}


@method_decorator(ensure_csrf_cookie, name="dispatch")
class MonitorView(TeacherMixin, TemplateView):
    template_name = T + "monitor.html"

    def get_context_data(self, **kwargs):
        exam = self.get_exam()
        # json_script-style escaping so student-controlled text can't break out of the <script> tag
        rows_json = json.dumps(dashboard.live_rows(exam)).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        return {**super().get_context_data(**kwargs), "exam": exam, "rows_json": rows_json}


class LiveJsonView(TeacherMixin, View):
    def get(self, request, exam_id: str) -> JsonResponse:
        return JsonResponse({"rows": dashboard.live_rows(self.get_exam())})


class StudentTimelineView(TeacherMixin, TemplateView):
    template_name = T + "timeline.html"

    def get_context_data(self, **kwargs):
        exam = self.get_exam()
        attempt = get_object_or_404(
            ExamAttempt.objects.select_related("student"), exam=exam, student__roll_number=self.kwargs["roll"]
        )
        return {**super().get_context_data(**kwargs), "exam": exam, "attempt": attempt, **dashboard.timeline(exam, attempt)}


class ScreenshotView(TeacherMixin, View):
    """Access-checked screenshot download (screenshots are never served from a public URL)."""

    def get(self, request, exam_id: str, pk: int) -> FileResponse:
        shot = get_object_or_404(ProctorScreenshot.objects.filter(exam=self.get_exam()), pk=pk)
        try:
            handle = shot.file.open("rb")
        except FileNotFoundError:
            raise Http404
        response = FileResponse(handle, content_type=mimetypes.guess_type(shot.file.name)[0] or "image/png")
        response["Cache-Control"] = "private, max-age=3600"
        return response


class CsvExportView(TeacherMixin, View):
    kind = "summary"

    def get(self, request, exam_id: str) -> HttpResponse:
        exam = self.get_exam()
        body = dashboard.events_csv(exam) if self.kind == "events" else dashboard.summary_csv(exam)
        response = HttpResponse(body, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{exam.exam_id}-{self.kind}.csv"'
        return response


class AttemptActionView(TeacherMixin, View):
    """POST-only JSON endpoints used by the monitor buttons (CSRF-protected)."""

    action = "force_end"

    def post(self, request, exam_id: str, pk: int) -> JsonResponse:
        attempts = ExamAttempt.objects.filter(exam=self.get_exam(), pk=pk)
        if not attempts.exists():
            raise Http404
        if self.action == "force_end":
            count = services.force_end_attempts(attempts, request.user.username)
        else:
            count = services.reset_attempts(attempts)
        return JsonResponse({"ok": True, "changed": count})


class MarksView(TeacherMixin, FormView):
    """Upload a Google Forms responses CSV; get a marks sheet that applies the proctoring policy."""

    template_name = T + "marks.html"
    form_class = MarksUploadForm

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "exam": self.get_exam()}

    def form_valid(self, form):
        exam = self.get_exam()
        try:
            rows, outside, used = marking.build_marks(
                dashboard.live_rows(exam),
                form.cleaned_data["responses"],
                form.cleaned_data["roll_column"].strip() or None,
                form.cleaned_data["score_column"].strip() or None,
            )
        except marking.MarkingError as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)
        if "download" in self.request.POST:
            response = HttpResponse(dashboard.marks_csv(rows), content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = f'attachment; filename="{exam.exam_id}-marks.csv"'
            return response
        return self.render_to_response(
            self.get_context_data(form=form, rows=rows, outside=outside, used=used, columns=marking.MARK_COLUMNS)
        )


class ExtraTimeView(TeacherMixin, View):
    """POST `minutes` (1-180) to give one student extra time."""

    def post(self, request, exam_id: str, pk: int) -> JsonResponse:
        attempts = ExamAttempt.objects.filter(exam=self.get_exam(), pk=pk)
        if not attempts.exists():
            raise Http404
        try:
            minutes = int(request.POST.get("minutes", ""))
        except ValueError:
            minutes = 0
        if not 1 <= minutes <= services.MAX_GRANT_MINUTES:
            return JsonResponse({"ok": False, "error": f"minutes must be 1-{services.MAX_GRANT_MINUTES}"}, status=400)
        return JsonResponse({"ok": True, "changed": services.add_extra_time(attempts, minutes, request.user.username)})


class BatchPasswordsView(TeacherMixin, View):
    """POST: give every not-yet-activated student of this exam's batch a first-time password (one-time sheet)."""

    def post(self, request, exam_id: str):
        exam = self.get_exam()
        back = f"/teacher/exams/{exam.exam_id}/"
        if exam.batch is None:
            response = password_sheet_response(
                request, [], f"{exam.name}", back,
                "This exam is open to all batches, so passwords can't be limited to one batch. Ask an admin to generate them.",
            )
            response.status_code = 400
            return response
        students = Student.objects.filter(batch=exam.batch, is_active=True, password="")
        rows = services.issue_first_time_passwords(students)
        return password_sheet_response(
            request, rows, f"{exam.name} · batch {exam.batch} · generated by {request.user.username}", back,
            f"Everyone in batch {exam.batch} already has a password. To replace one, ask an admin to use 'Generate first-time passwords'.",
        )
