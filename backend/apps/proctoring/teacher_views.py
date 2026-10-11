import json
import mimetypes

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.contrib import messages
from django.http import FileResponse, Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import FormView, TemplateView, UpdateView

from . import dashboard, marking, services
from .forms import ExamSettingsForm, MarksUploadForm, TeacherLoginForm
from .models import Exam, Student
from .teachers import is_teacher
from .sheets import password_sheet_response
from .models import ExamAttempt, ProctorScreenshot

T = "proctoring/teacher/"


class TeacherLoginView(LoginView):
    """Own login page: teachers never see or use the admin site."""

    template_name = T + "login.html"
    authentication_form = TeacherLoginForm
    redirect_authenticated_user = True
    next_page = "/teacher/"

    def get_success_url(self) -> str:
        return self.get_redirect_url() or "/teacher/"


class TeacherLogoutView(LogoutView):
    next_page = "/teacher/login/"


class TeacherMixin(LoginRequiredMixin):
    """Teachers (their own exams only) and administrators (all exams). Everyone else gets 403."""

    login_url = "/teacher/login/"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not is_teacher(request.user):
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
        show_archived = self.request.GET.get("archived") == "1"
        archived_count = exams.filter(archived=True).count()
        groups: dict = {}
        for exam in exams.filter(archived=False).order_by("batch", "name"):
            groups.setdefault(exam.batch, []).append(exam)
        archived = list(exams.filter(archived=True).order_by("-archived_at")) if show_archived else []
        # exams without a batch come first, as a warning: students cannot see them
        ordered = sorted(groups.items(), key=lambda item: (item[0] is not None, item[0] or 0))
        return {
            **super().get_context_data(**kwargs),
            "groups": [{"batch": batch, "exams": rows} for batch, rows in ordered],
            "archived": archived,
            "archived_count": archived_count,
            "show_archived": show_archived,
        }


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
        elif self.action == "advance":
            count = services.advance_attempts(attempts, request.user.username)
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
                "This exam has no batch yet. Ask an admin to set its batch first.",
            )
            response.status_code = 400
            return response
        students = Student.objects.filter(batch=exam.batch, is_active=True, password="")
        rows = services.issue_first_time_passwords(students)
        return password_sheet_response(
            request, rows, f"{exam.name} · batch {exam.batch} · generated by {request.user.username}", back,
            f"Everyone in batch {exam.batch} already has a password. To replace one, ask an admin to use 'Generate first-time passwords'.",
        )


class ExamSettingsView(TeacherMixin, UpdateView):
    """Schedule, parts, monitoring and webcam settings of one of the teacher's own exams."""

    template_name = T + "settings.html"
    form_class = ExamSettingsForm

    def get_object(self, queryset=None) -> Exam:
        return self.get_exam()

    def get_success_url(self) -> str:
        return f"/teacher/exams/{self.object.exam_id}/settings/?saved=1"

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "exam": self.object,
            "saved": self.request.GET.get("saved") == "1",
            "time_zone": settings.TIME_ZONE,
        }


class ExamArchiveView(TeacherMixin, View):
    """POST: archive or unarchive one of the teacher's exams."""

    archive = True

    def post(self, request, exam_id: str):
        exam = self.get_exam()
        try:
            if self.archive:
                services.archive_exam(exam, request.user.username)
                messages.success(request, f"{exam.name} is archived. Students no longer see it.")
            else:
                services.unarchive_exam(exam, request.user.username)
                messages.success(request, f"{exam.name} is active again.")
        except services.RuleError as e:
            messages.error(request, str(e))
        return redirect("teacher-monitor", exam_id=exam.exam_id)


class EvidenceDeleteView(TeacherMixin, TemplateView):
    """Delete an exam's screenshots and webcam photos (after it ended or was archived). Typing the exam id confirms."""

    template_name = T + "evidence.html"

    def context(self, exam, **extra):
        count, size = services.evidence_summary(exam)
        return {**self.get_context_data(), "exam": exam, "count": count, "size_kb": size // 1024,
                "allowed": services.can_delete_evidence(exam), **extra}

    def get(self, request, exam_id: str):
        return self.render_to_response(self.context(self.get_exam()))

    def post(self, request, exam_id: str):
        exam = self.get_exam()
        if request.POST.get("confirm", "").strip() != exam.exam_id:
            return self.render_to_response(self.context(exam, error=f"Type {exam.exam_id} exactly to confirm."))
        try:
            count, _ = services.delete_evidence(exam, request.user.username)
        except services.RuleError as e:
            return self.render_to_response(self.context(exam, error=str(e)))
        messages.success(request, f"Deleted {count} screenshot/photo file(s) of {exam.name}. The event log and marks are kept.")
        return redirect("teacher-monitor", exam_id=exam.exam_id)
