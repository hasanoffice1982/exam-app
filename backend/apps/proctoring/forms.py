from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.core.cache import cache
from django.core.exceptions import ValidationError

from . import marking, services
from .models import Exam
from .teachers import is_teacher


class MarksUploadForm(forms.Form):
    responses = forms.FileField(label="Google Forms responses (.csv)")
    roll_column = forms.CharField(required=False, label="Roll number column", help_text="Leave blank to detect")
    score_column = forms.CharField(required=False, label="Score column", help_text="Leave blank to detect")

    def clean_responses(self):
        upload = self.cleaned_data["responses"]
        if not upload.name.lower().endswith(".csv"):
            raise forms.ValidationError("Please upload a .csv file.")
        try:
            return marking.read_responses(upload.read(marking.MAX_UPLOAD_BYTES + 1))
        except marking.MarkingError as e:
            raise forms.ValidationError(str(e))


class TeacherLoginForm(AuthenticationForm):
    """Teacher/administrator login for the dashboard. Five wrong passwords lock that username for 15 minutes."""

    error_messages = {
        **AuthenticationForm.error_messages,
        "not_teacher": "This account is not a teacher account.",
        "locked": "Too many failed attempts. Try again in 15 minutes.",
    }

    def clean(self):
        key = f"teacher-login-fail:{(self.data.get('username') or '').strip().lower()}"
        try:
            services.check_lockout(key)
        except services.AuthError:
            raise ValidationError(self.error_messages["locked"], code="locked")
        try:
            cleaned = super().clean()
        except ValidationError:
            services.register_failure(key)
            raise
        cache.delete(key)
        return cleaned

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not is_teacher(user):
            raise ValidationError(self.error_messages["not_teacher"], code="not_teacher")


class ExamSettingsForm(forms.ModelForm):
    """What a teacher may change on their own exam. Name, batch and teachers stay with administrators."""

    _local = "%Y-%m-%dT%H:%M"

    class Meta:
        model = Exam
        fields = [
            "written_enabled", "form_url", "practical_enabled", "practical_instructions", "practical_url",
            "practical_screenshot_seconds", "starts_at", "ends_at", "grace_seconds", "monitoring_enabled",
            "webcam_enabled", "webcam_interval_seconds",
        ]
        widgets = {
            "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "practical_instructions": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("starts_at", "ends_at"):
            self.fields[name].input_formats = [self._local, "%Y-%m-%dT%H:%M:%S"]
