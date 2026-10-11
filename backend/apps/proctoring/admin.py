from django import forms
from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html

from . import services
from .sheets import password_sheet_response
from .models import (
    AuditEntry,
    BatchChange,
    Consent,
    Exam,
    ExamAttempt,
    ProctorEvent,
    ProctorScreenshot,
    Student,
    StudentToken,
)


# The admin site is for administrators (superusers) only. Teachers never log in here: they use the teacher
# dashboard (/teacher/), which has its own login and only shows their own exams.


class ReadOnlyLogAdmin(admin.ModelAdmin):
    """Evidence tables: nobody edits or adds rows by hand."""

    list_select_related = ("exam",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ("exam_id", "name", "batch", "written_enabled", "practical_enabled", "monitoring_enabled", "starts_at", "ends_at", "status")
    list_filter = ("archived", "batch")
    list_editable = ("monitoring_enabled",)
    search_fields = ("exam_id", "name")
    filter_horizontal = ("teachers",)
    actions = ["archive_selected", "unarchive_selected"]

    @admin.action(description="Archive selected exams (hide from students and default lists)")
    def archive_selected(self, request, queryset):
        for exam in queryset:
            try:
                services.archive_exam(exam, request.user.username)
                self.message_user(request, f"Archived {exam.name}.")
            except services.RuleError as e:
                self.message_user(request, f"{exam.name}: {e}", level=messages.ERROR)

    @admin.action(description="Unarchive selected exams")
    def unarchive_selected(self, request, queryset):
        for exam in queryset.filter(archived=True):
            services.unarchive_exam(exam, request.user.username)
        self.message_user(request, "Unarchived.")


@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    list_display = ("student", "exam", "stage", "status", "started_at", "ended_at", "last_seen")
    list_filter = ("exam", "status")
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
    list_filter = ("exam",)
    search_fields = ("student",)


@admin.register(ProctorEvent)
class ProctorEventAdmin(ReadOnlyLogAdmin):
    list_display = ("student", "exam", "event_type", "detail", "timestamp")
    list_filter = ("exam", "event_type")
    search_fields = ("student",)
    date_hierarchy = "timestamp"


@admin.register(ProctorScreenshot)
class ProctorScreenshotAdmin(ReadOnlyLogAdmin):
    list_display = ("student", "exam", "kind", "timestamp", "preview")
    list_filter = ("exam", "kind")
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
    actions = ["generate_passwords", "reset_activation", "deactivate_selected", "reactivate_selected"]

    def has_delete_permission(self, request, obj=None):
        # a student must be deactivated first: stops accidental deletion of records someone may still need
        return obj is None or not obj.is_active

    @admin.action(description="Deactivate selected students (no more logins; records are kept)")
    def deactivate_selected(self, request, queryset):
        count = services.deactivate_students(queryset, request.user.username)
        self.message_user(request, f"Deactivated {count} student(s) and ended their sessions.")

    @admin.action(description="Reactivate selected students")
    def reactivate_selected(self, request, queryset):
        count = queryset.filter(is_active=False).update(is_active=True)
        self.message_user(request, f"Reactivated {count} student(s).")

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


@admin.register(AuditEntry)
class AuditEntryAdmin(admin.ModelAdmin):
    """Read-only record of archives and evidence deletions."""

    list_display = ("at", "action", "exam_label", "detail", "performed_by")
    list_filter = ("action",)
    search_fields = ("exam_label", "performed_by")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
