from django import forms
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from . import services
from .sheets import password_sheet_response
from .models import (
    BatchChange,
    Consent,
    Exam,
    ExamAttempt,
    ProctorEvent,
    ProctorScreenshot,
    Student,
    StudentToken,
)


# ---- teacher scoping -------------------------------------------------------------------------
# Superusers see everything. Teachers (staff in the "Teachers" group) only see data of exams
# that list them in Exam.teachers; objects outside that set 404 in the admin.


class ExamFilter(admin.SimpleListFilter):
    title = "exam"
    parameter_name = "exam_slug"

    def lookups(self, request, model_admin):
        exams = Exam.objects.all() if request.user.is_superuser else Exam.objects.filter(teachers=request.user)
        return [(e.exam_id, e.name) for e in exams]

    def queryset(self, request, queryset):
        return queryset.filter(exam__exam_id=self.value()) if self.value() else queryset


class TeacherScopedAdmin(admin.ModelAdmin):
    exam_lookup = "exam"  # path from the model to its Exam

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(**{f"{self.exam_lookup}__teachers": request.user}).distinct()


class ReadOnlyLogAdmin(TeacherScopedAdmin):
    """Evidence tables: nobody edits or adds rows by hand."""

    list_select_related = ("exam",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ---- exams -----------------------------------------------------------------------------------


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ("exam_id", "name", "batch", "mode", "monitoring_enabled", "starts_at", "ends_at", "status")
    list_editable = ("monitoring_enabled",)
    search_fields = ("exam_id", "name")
    filter_horizontal = ("teachers",)
    TEACHER_READONLY = ("exam_id", "name", "batch", "mode", "teachers")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs if request.user.is_superuser else qs.filter(teachers=request.user)

    def get_readonly_fields(self, request, obj=None):
        return () if request.user.is_superuser else self.TEACHER_READONLY

    def has_add_permission(self, request):
        return request.user.is_superuser and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser and super().has_delete_permission(request, obj)


@admin.register(ExamAttempt)
class ExamAttemptAdmin(TeacherScopedAdmin):
    list_display = ("student", "exam", "status", "started_at", "ended_at", "last_seen")
    list_filter = (ExamFilter, "status")
    search_fields = ("student__roll_number", "student__name")
    list_select_related = ("exam", "student", "student__token")
    actions = ["force_end", "reset_attempt"]

    @admin.display(description="Last seen")
    def last_seen(self, obj: ExamAttempt):
        token = getattr(obj.student, "token", None)
        return token.last_seen_at if token else None

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    @admin.action(description="Force end selected attempts (kicks the student out)", permissions=["change"])
    def force_end(self, request, queryset):
        count = services.force_end_attempts(queryset, request.user.username)
        self.message_user(request, f"Ended {count} attempt(s).")

    @admin.action(description="Reset selected attempts (lets the student start again)", permissions=["change"])
    def reset_attempt(self, request, queryset):
        self.message_user(request, f"Reset {services.reset_attempts(queryset)} attempt(s).")


@admin.register(Consent)
class ConsentAdmin(ReadOnlyLogAdmin):
    list_display = ("student", "exam", "timestamp")
    list_filter = (ExamFilter,)
    search_fields = ("student",)


@admin.register(ProctorEvent)
class ProctorEventAdmin(ReadOnlyLogAdmin):
    list_display = ("student", "exam", "event_type", "detail", "timestamp")
    list_filter = (ExamFilter, "event_type")
    search_fields = ("student",)
    date_hierarchy = "timestamp"


@admin.register(ProctorScreenshot)
class ProctorScreenshotAdmin(ReadOnlyLogAdmin):
    list_display = ("student", "exam", "kind", "timestamp", "preview")
    list_filter = (ExamFilter, "kind")
    search_fields = ("student",)
    date_hierarchy = "timestamp"
    readonly_fields = ("preview",)

    @admin.display(description="Preview")
    def preview(self, obj: ProctorScreenshot) -> str:
        if not obj.file:
            return "-"
        url = reverse("teacher-screenshot", args=[obj.exam.exam_id, obj.pk])  # access-checked, not a public media URL
        return format_html('<a href="{0}" target="_blank"><img src="{0}" style="height:60px"></a>', url)


# ---- students (superusers only: teachers have no Student permissions) ----------------------------


class StudentAdminForm(forms.ModelForm):
    new_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Optional. Students normally get an auto-generated password on first activation.",
    )

    class Meta:
        model = Student
        fields = ["roll_number", "name", "email", "batch", "is_active"]


class BatchChangeInline(admin.TabularInline):
    model = BatchChange
    extra = 0
    can_delete = False
    readonly_fields = ("from_batch", "to_batch", "changed_at", "changed_by")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    form = StudentAdminForm
    inlines = [BatchChangeInline]
    list_display = ("roll_number", "name", "batch", "email", "activated", "is_active")
    list_filter = ("batch", "is_active")
    search_fields = ("roll_number", "name")
    actions = ["generate_passwords", "reset_activation"]

    @admin.display(boolean=True, description="Activated")
    def activated(self, obj: Student) -> bool:
        return obj.is_activated

    @admin.action(description="Generate first-time passwords (shown once, for printing)")
    def generate_passwords(self, request, queryset):
        rows = services.issue_first_time_passwords(queryset.filter(is_active=True))
        return password_sheet_response(
            request, rows, f"{len(rows)} student(s) · generated by {request.user.username}", "/admin/proctoring/student/"
        )

    @admin.action(description="Reset activation (clear password so the student can activate again)")
    def reset_activation(self, request, queryset):
        count = queryset.update(password="")
        self.message_user(request, f"Reset {count} student(s).")

    def save_model(self, request, obj, form, change):
        if form.cleaned_data.get("new_password"):
            obj.set_password(form.cleaned_data["new_password"])
        obj._changed_by = request.user.username
        super().save_model(request, obj, form, change)


@admin.register(StudentToken)
class StudentTokenAdmin(admin.ModelAdmin):
    """Active sessions. Deleting a row revokes it (the student's exam window closes at its next heartbeat)."""

    list_display = ("student", "issued_at", "last_seen_at", "expires_at")
    list_select_related = ("student",)
    readonly_fields = ("student", "key_hash", "issued_at", "expires_at", "last_seen_at")

    def has_add_permission(self, request):
        return False
