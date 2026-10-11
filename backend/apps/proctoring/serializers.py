from django.utils import timezone
from rest_framework import serializers

from .models import Consent, Exam, ProctorEvent, ProctorScreenshot


class ExamListSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)

    class Meta:
        model = Exam
        fields = ["exam_id", "name", "starts_at", "ends_at", "status"]


class ExamConfigSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)
    server_time = serializers.SerializerMethodField()

    class Meta:
        model = Exam
        fields = [
            "monitoring_enabled", "form_url", "mode", "starts_at", "ends_at", "grace_seconds",
            "webcam_enabled", "webcam_interval_seconds", "status", "server_time",
        ]

    def get_server_time(self, obj: Exam) -> str:
        return timezone.now().isoformat()

    def validate(self, attrs):
        starts = attrs.get("starts_at", getattr(self.instance, "starts_at", None))
        ends = attrs.get("ends_at", getattr(self.instance, "ends_at", None))
        if starts and ends and ends <= starts:
            raise serializers.ValidationError("ends_at must be after starts_at.")
        return attrs


class _ClientIdMixin(serializers.Serializer):
    # Declared explicitly so DRF doesn't add a UniqueValidator (extra query + 400): the view dedups instead.
    client_id = serializers.UUIDField(required=False, allow_null=True)


class _ExamRefMixin(serializers.Serializer):
    """Lets clients reference the exam by its public `exam_id` slug."""

    exam_id = serializers.SlugRelatedField(
        source="exam", slug_field="exam_id", queryset=Exam.objects.all()
    )


class ConsentSerializer(_ExamRefMixin, serializers.ModelSerializer):
    student = serializers.CharField(read_only=True)  # taken from the session token

    class Meta:
        model = Consent
        fields = ["id", "student", "exam_id", "timestamp"]


class ProctorEventSerializer(_ClientIdMixin, _ExamRefMixin, serializers.ModelSerializer):
    student = serializers.CharField(read_only=True)

    class Meta:
        model = ProctorEvent
        fields = ["id", "student", "exam_id", "event_type", "detail", "timestamp", "client_id"]


MAX_SCREENSHOT_BYTES = 10 * 1024 * 1024
ALLOWED_SCREENSHOT_TYPES = {"image/png", "image/jpeg"}


class ProctorScreenshotSerializer(_ClientIdMixin, _ExamRefMixin, serializers.ModelSerializer):
    student = serializers.CharField(read_only=True)

    class Meta:
        model = ProctorScreenshot
        fields = ["id", "student", "exam_id", "kind", "file", "timestamp", "client_id"]

    def validate_file(self, value):
        if value.size > MAX_SCREENSHOT_BYTES:
            raise serializers.ValidationError("File too large (max 10 MB).")
        if getattr(value, "content_type", None) not in ALLOWED_SCREENSHOT_TYPES:
            raise serializers.ValidationError("Only PNG or JPEG images are accepted.")
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
