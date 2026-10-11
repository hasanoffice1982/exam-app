from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


def screenshot_upload_path(instance: "ProctorScreenshot", filename: str) -> str:
    student = slugify(instance.student) or "unknown"
    return f"screenshots/{instance.exam.exam_id}/{student}/{filename}"


class Student(models.Model):
    roll_number = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    password = models.CharField(max_length=128, blank=True)  # hashed; blank = not activated yet
    is_active = models.BooleanField(default=True)
    batch = models.PositiveIntegerField(null=True, blank=True, help_text="Batch number. Can only move forward.")

    # DRF treats any object with these attributes as an authenticated user.
    is_authenticated = True
    is_anonymous = False

    class Meta:
        ordering = ["roll_number"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._loaded_batch = self.batch  # remembered so we can enforce forward-only moves without a query

    @property
    def label(self) -> str:
        return f"{self.name} ({self.roll_number})"

    def batch_change_error(self) -> str | None:
        """Batches only move forward (81 -> 82 or 85, never 95 -> 94). First assignment is free."""
        before = self._loaded_batch
        if self._state.adding or before is None or self.batch == before:
            return None
        if self.batch is None or self.batch < before:
            return f"Batch can only move forward (currently {before})."
        return None

    def clean(self) -> None:
        super().clean()
        error = self.batch_change_error()
        if error:
            raise ValidationError({"batch": error})

    def save(self, *args, **kwargs):
        error = self.batch_change_error()
        if error:
            raise ValidationError({"batch": error})
        moved = not self._state.adding and self.batch != self._loaded_batch
        previous = self._loaded_batch
        super().save(*args, **kwargs)
        if moved:
            BatchChange.objects.create(
                student=self, from_batch=previous, to_batch=self.batch, changed_by=getattr(self, "_changed_by", "")
            )
        self._loaded_batch = self.batch

    @property
    def is_activated(self) -> bool:
        return bool(self.password)

    def set_password(self, raw_password: str) -> None:
        self.password = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password(raw_password, self.password)

    def __str__(self) -> str:
        return f"{self.name} ({self.roll_number})"


class BatchChange(models.Model):
    """Audit trail of batch moves."""

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="batch_changes")
    from_batch = models.PositiveIntegerField(null=True, blank=True)
    to_batch = models.PositiveIntegerField(null=True, blank=True)
    changed_at = models.DateTimeField(default=timezone.now)
    changed_by = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ["-changed_at"]


class StudentToken(models.Model):
    """One active session per student: issuing a new token replaces the old one."""

    student = models.OneToOneField(Student, on_delete=models.CASCADE, related_name="token")
    key_hash = models.CharField(max_length=64, unique=True)  # sha256 of the bearer token
    issued_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    last_seen_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"session of {self.student_id}"


class Exam(models.Model):
    """An exam has a written part (Google Form), a practical part, or both. Order is fixed: written, then practical."""

    exam_id = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=200)
    form_url = models.URLField(max_length=500, blank=True, help_text="Google Form link (needed when the written part is on)")
    monitoring_enabled = models.BooleanField(default=True)
    written_enabled = models.BooleanField(default=True, help_text="Written part: the Google Form in a locked full-screen window")
    practical_enabled = models.BooleanField(
        default=False, help_text="Practical part (after the written part): free window, screenshots on a timer"
    )
    practical_instructions = models.TextField(blank=True, help_text="Shown to students in the practical window")
    practical_url = models.URLField(max_length=500, blank=True, help_text="Optional link opened from the practical window")
    practical_screenshot_seconds = models.PositiveSmallIntegerField(
        default=60,
        validators=[MinValueValidator(15), MaxValueValidator(600)],
        help_text="Average time between screenshots in the practical part (randomised +/-50%)",
    )
    batch = models.PositiveIntegerField(null=True, blank=False, help_text="The one batch that takes this exam. Required: every exam belongs to exactly one batch")
    teachers = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="exams_taught", limit_choices_to={"groups__name": "Teachers"},
        help_text="Teachers who can monitor this exam, end student attempts and edit its schedule (they use the teacher dashboard, never /admin/)",
    )
    starts_at = models.DateTimeField(null=True, blank=True, help_text="Empty = no start restriction")
    ends_at = models.DateTimeField(null=True, blank=True, help_text="Empty = no end time")
    webcam_enabled = models.BooleanField(default=False, help_text="Require the camera and take periodic photos")
    webcam_interval_seconds = models.PositiveSmallIntegerField(
        default=180,
        validators=[MinValueValidator(30), MaxValueValidator(3600)],
        help_text="Average time between webcam photos (randomised +/-50%)",
    )
    grace_seconds = models.PositiveSmallIntegerField(
        default=3, help_text="Switching away for less than this many seconds is ignored"
    )
    archived = models.BooleanField(default=False, help_text="Finished and published: hidden from students and from the default teacher list")
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def is_open_to(self, student: "Student") -> bool:
        return self.batch is not None and self.batch == student.batch  # no batch set = nobody can take it yet

    def clean(self) -> None:
        super().clean()
        errors = {}
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            errors["ends_at"] = "The end time must be after the start time."
        if not (self.written_enabled or self.practical_enabled):
            errors["written_enabled"] = "Turn on the written part, the practical part, or both."
        if self.written_enabled and not self.form_url:
            errors["form_url"] = "The written part needs a Google Form link."
        if self.practical_enabled and not (self.practical_instructions.strip() or self.practical_url):
            errors["practical_instructions"] = "The practical part needs instructions or a link."
        if errors:
            raise ValidationError(errors)

    @property
    def first_stage(self) -> str:
        return "written" if self.written_enabled else "practical"

    def status_with_extra(self, extra_minutes: int = 0) -> str:
        now = timezone.now()
        if self.starts_at and now < self.starts_at:
            return "upcoming"
        if self.ends_at and now > self.ends_at + timedelta(minutes=extra_minutes):
            return "closed"
        return "open"

    @property
    def status(self) -> str:
        return self.status_with_extra(0)

    def __str__(self) -> str:
        return f"{self.name} ({self.exam_id})"


class AuditEntry(models.Model):
    """Who archived, unarchived or deleted evidence, and when. Never edited by hand."""

    exam = models.ForeignKey(Exam, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_entries")
    exam_label = models.CharField(max_length=300, blank=True)  # survives the exam being deleted
    action = models.CharField(max_length=40)
    detail = models.CharField(max_length=300, blank=True)
    performed_by = models.CharField(max_length=150)
    at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-at"]
        verbose_name_plural = "audit entries"

    def __str__(self) -> str:
        return f"{self.action} by {self.performed_by} on {self.exam_label}"


class ExamAttempt(models.Model):
    """One attempt per student per exam. Quitting or a forced end is final until a teacher resets it."""

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        QUIT = "quit", "Quit by student"
        COMPLETED = "completed", "Completed (time up)"
        FORCE_ENDED = "force_ended", "Ended by teacher"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="attempts")
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="attempts")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_PROGRESS)
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    extra_minutes = models.PositiveSmallIntegerField(default=0, help_text="Extra time given to this student by a teacher")

    class Stage(models.TextChoices):
        WRITTEN = "written", "Written part"
        PRACTICAL = "practical", "Practical part"

    stage = models.CharField(max_length=10, choices=Stage.choices, default=Stage.WRITTEN)

    @property
    def ends_at(self):
        """This student's own deadline: the exam's end plus any extra time (None = no deadline)."""
        if self.exam.ends_at is None:
            return None
        return self.exam.ends_at + timedelta(minutes=self.extra_minutes)

    class Meta:
        ordering = ["-started_at"]
        constraints = [models.UniqueConstraint(fields=["student", "exam"], name="one_attempt_per_student_exam")]

    def __str__(self) -> str:
        return f"{self.student_id} / {self.exam_id}: {self.status}"


class Consent(models.Model):
    student = models.CharField(max_length=200)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="consents")
    timestamp = models.DateTimeField(default=timezone.now)

    def __str__(self) -> str:
        return f"{self.student} consented @ {self.timestamp:%Y-%m-%d %H:%M:%S}"


class ProctorEvent(models.Model):
    student = models.CharField(max_length=200)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=50)
    detail = models.CharField(max_length=200, blank=True, help_text="e.g. blocked app name, display count")
    timestamp = models.DateTimeField(default=timezone.now)
    client_id = models.UUIDField(null=True, blank=True, help_text="Client-generated; makes retries idempotent")

    class Meta:
        ordering = ["-timestamp"]
        indexes = [models.Index(fields=["exam", "timestamp"], name="event_exam_ts_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=["client_id"], condition=models.Q(client_id__isnull=False), name="event_client_id_uniq"
            )
        ]

    def __str__(self) -> str:
        return f"{self.student} {self.event_type} @ {self.timestamp:%H:%M:%S}"


class ProctorScreenshot(models.Model):
    """A captured image: the student's screen or their webcam."""

    class Kind(models.TextChoices):
        SCREEN = "screen", "Screenshot"
        WEBCAM = "webcam", "Webcam photo"

    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.SCREEN)
    student = models.CharField(max_length=200)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="screenshots")
    file = models.FileField(upload_to=screenshot_upload_path)
    timestamp = models.DateTimeField(default=timezone.now)
    client_id = models.UUIDField(null=True, blank=True, help_text="Client-generated; makes retries idempotent")

    class Meta:
        ordering = ["-timestamp"]
        indexes = [models.Index(fields=["exam", "timestamp"], name="shot_exam_ts_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=["client_id"], condition=models.Q(client_id__isnull=False), name="shot_client_id_uniq"
            )
        ]

    def __str__(self) -> str:
        return f"{self.student} screenshot @ {self.timestamp:%H:%M:%S}"
