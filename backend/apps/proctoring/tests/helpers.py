import shutil
import tempfile

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIClient

from apps.proctoring import services
from apps.proctoring.models import Exam, Student

PASSWORD = "S3cure-test-pw"


DEFAULT_BATCH = 81  # students and exams share a batch unless a test says otherwise


def make_exam(exam_id: str = "math-101", **kwargs) -> Exam:
    kwargs.setdefault("name", exam_id)
    kwargs.setdefault("batch", DEFAULT_BATCH)
    kwargs.setdefault("form_url", "https://example.com/form")
    return Exam.objects.create(exam_id=exam_id, **kwargs)


def make_student(
    roll: str = "1", name: str = "Ann", email: str = "ann@example.com", activated: bool = True, batch: int | None = DEFAULT_BATCH
) -> Student:
    student = Student(roll_number=roll, name=name, email=email, batch=batch)
    if activated:
        student.set_password(PASSWORD)
    student.save()
    return student


def authed_client(student: Student) -> tuple[APIClient, str]:
    token = services.issue_token(student)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client, token


def png(name: str = "s.png") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, b"\x89PNG\r\n\x1a\nfake", content_type="image/png")


class IsolatedMixin:
    """Fresh cache (throttles/lockouts) and a throwaway MEDIA_ROOT for every test."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self._media = tempfile.mkdtemp()
        override = override_settings(MEDIA_ROOT=self._media)
        override.enable()
        self.addCleanup(override.disable)
        self.addCleanup(shutil.rmtree, self._media, True)
