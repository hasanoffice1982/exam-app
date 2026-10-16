from datetime import timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers

from .event_types import CLIENT_SENDABLE
from .models import Consent, Exam, ProctorEvent, ProctorScreenshot


class ExamListSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)

    class Meta:
        model = Exam
        fields = ["exam_id", "name", "starts_at", "ends_at", "status"]


class ExamConfigSerializer(serializers.ModelSerializer):
    name = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    server_time = serializers.SerializerMethodField()

    class Meta:
        model = Exam
        fields = [
            "name", "monitoring_enabled", "form_url", "written_enabled", "practical_enabled", "practical_instructions",
            "practical_url", "practical_screenshot_seconds", "starts_at", "ends_at", "grace_seconds",
            "webcam_enabled", "webcam_interval_seconds", "status", "server_time",
        ]

    def get_server_time(self, obj: Exam) -> str:
        return timezone.now().isoformat()

    def validate(self, attrs):
        """Same rules as the admin and the teacher settings page: run the model's own clean() on the merged values."""
        merged = Exam(**{f: getattr(self.instance, f) for f in self.Meta.fields if hasattr(self.instance, f) and f not in ("status", "server_time", "name")})
        for key, value in attrs.items():
            setattr(merged, key, value)
        merged.batch = self.instance.batch
        try:
            merged.clean()
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message_dict)
        return attrs


class _ClientIdMixin(serializers.Serializer):
    # Declared explicitly so DRF doesn't add a UniqueValidator (extra query + 400): the view dedups instead.
    client_id = serializers.UUIDField(required=False, allow_null=True)


class _ExamRefMixin(serializers.Serializer):
    """Lets clients reference the exam by its public `exam_id` slug, and only exams of the student's own batch."""

    exam_id = serializers.SlugRelatedField(
        source="exam", slug_field="exam_id", queryset=Exam.objects.all()
    )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get("request")
        exam = attrs.get("exam")
        if request is not None and exam is not None and not exam.is_open_to(request.user):
            raise serializers.ValidationError({"exam_id": "This exam is not assigned to you."})
        return attrs


class _TimestampMixin(serializers.Serializer):
    """Client clocks can be wrong: never accept a time in the future (clamped to now), but never drop the event."""

    def validate_timestamp(self, value):
        return min(value, timezone.now())


class ConsentSerializer(_TimestampMixin, _ExamRefMixin, serializers.ModelSerializer):
    student = serializers.CharField(read_only=True)  # taken from the session token

    class Meta:
        model = Consent
        fields = ["id", "student", "exam_id", "timestamp"]


class ProctorEventSerializer(_TimestampMixin, _ClientIdMixin, _ExamRefMixin, serializers.ModelSerializer):
    student = serializers.CharField(read_only=True)
    event_type = serializers.ChoiceField(choices=CLIENT_SENDABLE)  # server-written types cannot be forged

    class Meta:
        model = ProctorEvent
        fields = ["id", "student", "exam_id", "event_type", "detail", "timestamp", "client_id"]


MAX_SCREENSHOT_BYTES = 10 * 1024 * 1024
ALLOWED_SCREENSHOT_TYPES = {"image/png", "image/jpeg"}


IMAGE_SIGNATURES = {".png": (b"\x89PNG\r\n\x1a\n",), ".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",)}


class ProctorScreenshotSerializer(_TimestampMixin, _ClientIdMixin, _ExamRefMixin, serializers.ModelSerializer):
    student = serializers.CharField(read_only=True)

    class Meta:
        model = ProctorScreenshot
        fields = ["id", "student", "exam_id", "kind", "file", "timestamp", "client_id"]

    def validate_file(self, value):
        if value.size > MAX_SCREENSHOT_BYTES:
            raise serializers.ValidationError("File too large (max 10 MB).")
        if getattr(value, "content_type", None) not in ALLOWED_SCREENSHOT_TYPES:
            raise serializers.ValidationError("Only PNG or JPEG images are accepted.")
        extension = "." + value.name.rsplit(".", 1)[-1].lower() if "." in value.name else ""
        header = value.read(8)
        value.seek(0)
        if extension not in IMAGE_SIGNATURES or not any(header.startswith(sig) for sig in IMAGE_SIGNATURES[extension]):
            raise serializers.ValidationError("The file is not a real PNG or JPEG image.")  # also keeps .html etc. out
        return value


class ActivateSerializer(serializers.Serializer):
    roll_number = serializers.CharField(max_length=50)
    email = serializers.EmailField()


class LoginSerializer(serializers.Serializer):
    roll_number = serializers.CharField(max_length=50)
    password = serializers.CharField(max_length=128)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(max_length=128)
    new_password = serializers.CharField(max_length=128)  # length/rules are checked in the service for clear messages


class ProfileSerializer(serializers.Serializer):
    roll_number = serializers.CharField()
    name = serializers.CharField()
    email = serializers.SerializerMethodField()
    batch = serializers.IntegerField(allow_null=True)

    def get_email(self, obj) -> str:
        from .services import mask_email

        return mask_email(obj.email) if obj.email else ""
