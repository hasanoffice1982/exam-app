# Auth: students authenticate with a bearer session token (see authentication.py). Everything is
# deny-by-default (IsStudent); only login/activate are public and the config write needs X-Admin-Key.
# TODO: serve over HTTPS before exposing beyond a trusted network.
import logging
from datetime import timedelta

from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import ListAPIView
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import services
from .event_types import EventType
from .models import Consent, Exam, ExamAttempt, ProctorEvent, ProctorScreenshot, StudentToken
from .permissions import HasAdminKey, IsStudent
from .serializers import (
    ActivateSerializer,
    ChangePasswordSerializer,
    ConsentSerializer,
    ExamConfigSerializer,
    ExamListSerializer,
    LoginSerializer,
    ProfileSerializer,
    ProctorEventSerializer,
    ProctorScreenshotSerializer,
)
from .throttles import HoneypotBlockThrottle, client_ip, trip_honeypot

logger = logging.getLogger(__name__)

GENERIC_LOGIN_ERROR = {"detail": "Invalid roll number or password."}


class PublicAuthView(APIView):
    """Base for login/activate: unauthenticated, IP-throttled and protected by a honeypot field."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [HoneypotBlockThrottle, ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request) -> Response:
        if trip_honeypot(request):
            logger.warning("Honeypot tripped from %s", request.META.get("REMOTE_ADDR"))
            return Response(GENERIC_LOGIN_ERROR, status=status.HTTP_401_UNAUTHORIZED)
        return self.handle(request)

    def handle(self, request) -> Response:
        raise NotImplementedError


class LoginView(PublicAuthView):
    def handle(self, request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            student = services.authenticate_student(data["roll_number"].strip(), data["password"], client_ip(request))
        except services.AuthError as e:
            body = {"detail": e.message}
            if e.status == status.HTTP_401_UNAUTHORIZED and "not activated" in e.message:
                body["code"] = "not_activated"
            return Response(body, status=e.status)
        token = services.issue_token(student)
        return Response(
            {"roll_number": student.roll_number, "name": student.name, "batch": student.batch, "token": token}
        )


class ActivateView(PublicAuthView):
    """First-time activation: if roll number + email match, the password is emailed (never returned here)."""

    def handle(self, request) -> Response:
        serializer = ActivateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            masked = services.activate_student(data["roll_number"].strip(), data["email"], client_ip(request))
        except services.AuthError as e:
            return Response({"detail": e.message}, status=e.status)
        return Response({"detail": f"We emailed your password to {masked}. Check your inbox (and spam), then log in.", "email": masked})


class AccountView(APIView):
    """Base for the signed-in student's own account endpoints."""

    permission_classes = [IsStudent]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "account"


class ProfileView(AccountView):
    """GET: the student's own details (no extra queries: the session already loaded the student)."""

    def get(self, request) -> Response:
        return Response(ProfileSerializer(request.user).data)


class ChangePasswordView(AccountView):
    def post(self, request) -> Response:
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            services.change_password(
                request.user, serializer.validated_data["current_password"], serializer.validated_data["new_password"],
                client_ip(request),
            )
        except services.AuthError as e:
            return Response({"detail": e.message}, status=e.status)
        return Response({"detail": "Password changed."})


class LogoutView(AccountView):
    """Revokes the current session so a copied token stops working."""

    def post(self, request) -> Response:
        request.auth.delete()
        return Response({"detail": "Logged out."})


class HeartbeatView(APIView):
    """Called every ~30s by the exam window; lets teachers see who dropped off."""

    permission_classes = [IsStudent]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "heartbeat"

    def post(self, request) -> Response:
        StudentToken.objects.filter(pk=request.auth.pk).update(last_seen_at=timezone.now())
        return Response({"ok": True, "server_time": timezone.now().isoformat()})


class ExamListView(ListAPIView):
    """Only exams assigned to the student's own batch."""

    serializer_class = ExamListSerializer
    permission_classes = [IsStudent]
    pagination_class = None

    def get_queryset(self):
        batch = self.request.user.batch
        return Exam.objects.filter(batch=batch, archived=False) if batch is not None else Exam.objects.none()


def exam_for_student(request, exam_id: str) -> Exam:
    """The exam, if it exists and is assigned to the student's batch; otherwise 404 / 403 with a reason."""
    exam = get_object_or_404(Exam, exam_id=exam_id)
    if not exam.is_open_to(request.user):
        raise PermissionDenied("This exam is not assigned to your batch.")
    if exam.archived:
        raise PermissionDenied("This exam has been archived.")
    return exam


def config_for(exam: Exam, student, attempt: ExamAttempt | None = None) -> dict:
    """The exam config as this student sees it: their own deadline, status and current stage.

    Costs one query for the student's attempt unless the caller already has it.
    """
    if attempt is None:
        attempt = ExamAttempt.objects.filter(exam=exam, student=student).only("extra_minutes", "stage").first()
    extra_minutes = attempt.extra_minutes if attempt else 0
    data = ExamConfigSerializer(exam).data
    if exam.ends_at and extra_minutes:
        data["ends_at"] = serializers.DateTimeField().to_representation(exam.ends_at + timedelta(minutes=extra_minutes))
    data["status"] = exam.status_with_extra(extra_minutes)
    data["stage"] = attempt.stage if attempt else exam.first_stage
    return data


class ExamConfigView(APIView):
    """GET (student session) returns the exam config; POST (X-Admin-Key) partially updates it."""

    def get_permissions(self):
        return [HasAdminKey()] if self.request.method == "POST" else [IsStudent()]

    def get(self, request, exam_id: str) -> Response:
        exam = exam_for_student(request, exam_id)
        return Response(config_for(exam, request.user))

    def post(self, request, exam_id: str) -> Response:
        exam = get_object_or_404(Exam, exam_id=exam_id)
        serializer = ExamConfigSerializer(exam, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


ATTEMPT_ENDED_MESSAGES = {
    ExamAttempt.Status.QUIT: "You quit this exam and cannot re-enter it.",
    ExamAttempt.Status.COMPLETED: "You have already completed this exam.",
    ExamAttempt.Status.FORCE_ENDED: "Your teacher ended your attempt. Contact them to continue.",
}


class ExamStartView(APIView):
    """Begins (or resumes) the student's single attempt and returns the exam config."""

    permission_classes = [IsStudent]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "heartbeat"

    def post(self, request, exam_id: str) -> Response:
        exam = exam_for_student(request, exam_id)
        attempt = ExamAttempt.objects.filter(student=request.user, exam=exam).first()
        extra = attempt.extra_minutes if attempt else 0
        exam_status = exam.status_with_extra(extra)
        if exam_status != "open":
            raise PermissionDenied("This exam has not started yet." if exam_status == "upcoming" else "This exam has ended.")
        created = attempt is None
        if attempt is None:
            try:
                attempt = ExamAttempt.objects.create(student=request.user, exam=exam, stage=exam.first_stage)
            except IntegrityError:  # two windows racing: the other one won
                attempt = ExamAttempt.objects.get(student=request.user, exam=exam)
        if attempt.status != ExamAttempt.Status.IN_PROGRESS:
            raise PermissionDenied(ATTEMPT_ENDED_MESSAGES[attempt.status])
        if not created:  # reopening after a crash/restart is allowed, but leaves a trace for the teacher
            ProctorEvent.objects.create(student=request.user.label, exam=exam, event_type=EventType.EXAM_RESUMED)
        return Response(config_for(exam, request.user, attempt))


class ExamAdvanceView(APIView):
    """Written part done -> practical part. One way only; repeating the call is harmless."""

    permission_classes = [IsStudent]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "heartbeat"

    def post(self, request, exam_id: str) -> Response:
        exam = exam_for_student(request, exam_id)
        attempt = ExamAttempt.objects.filter(student=request.user, exam=exam).first()
        if attempt is None:
            raise PermissionDenied("Start the exam first.")
        if attempt.status != ExamAttempt.Status.IN_PROGRESS:
            raise PermissionDenied(ATTEMPT_ENDED_MESSAGES[attempt.status])
        if attempt.stage == ExamAttempt.Stage.WRITTEN:
            if not exam.practical_enabled:
                return Response({"detail": "This exam has no practical part."}, status=status.HTTP_400_BAD_REQUEST)
            services.advance_to_practical(attempt, "student")
        return Response(config_for(exam, request.user, attempt))


class StudentCreateViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    """POST-only; the student identity always comes from the session, never from the request body."""

    permission_classes = [IsStudent]
    throttle_classes = [ScopedRateThrottle]

    def perform_create(self, serializer) -> None:
        serializer.save(student=self.request.user.label)


class IdempotentCreateMixin:
    """Retries with the same `client_id` return the original row instead of inserting a duplicate.

    The happy path is a single INSERT; the unique constraint does the dedup.
    """

    def create(self, request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        model = serializer.Meta.model
        instance = model(**{**serializer.validated_data, "student": request.user.label})
        try:
            instance.save()
        except IntegrityError:
            for field in model._meta.get_fields():
                stored = getattr(instance, field.name, None) if field.get_internal_type() == "FileField" else None
                if stored:
                    stored.storage.delete(stored.name)  # don't leave an orphan upload behind
            existing = model.objects.filter(client_id=serializer.validated_data.get("client_id")).first()
            if existing is None or existing.student != request.user.label:
                return Response({"detail": "Conflict."}, status=status.HTTP_409_CONFLICT)
            return Response(self.get_serializer(existing).data, status=status.HTTP_200_OK)
        self.after_create(instance, request)
        return Response(self.get_serializer(instance).data, status=status.HTTP_201_CREATED)

    def after_create(self, instance, request) -> None:
        pass


class ConsentViewSet(StudentCreateViewSet):
    queryset = Consent.objects.none()
    serializer_class = ConsentSerializer
    throttle_scope = "events"


# Events that close the student's attempt (only these cost an extra query).
ATTEMPT_ENDING_EVENTS = {
    EventType.EXAM_QUIT: ExamAttempt.Status.QUIT,
    EventType.TIME_UP: ExamAttempt.Status.COMPLETED,
    EventType.EXAM_FINISHED: ExamAttempt.Status.COMPLETED,
}


class ProctorEventViewSet(IdempotentCreateMixin, StudentCreateViewSet):
    queryset = ProctorEvent.objects.none()
    serializer_class = ProctorEventSerializer
    throttle_scope = "events"

    def after_create(self, instance, request) -> None:
        new_status = ATTEMPT_ENDING_EVENTS.get(instance.event_type)
        if new_status:
            ExamAttempt.objects.filter(
                student=request.user, exam_id=instance.exam_id, status=ExamAttempt.Status.IN_PROGRESS
            ).update(status=new_status, ended_at=timezone.now())


class ProctorScreenshotViewSet(IdempotentCreateMixin, StudentCreateViewSet):
    queryset = ProctorScreenshot.objects.none()
    serializer_class = ProctorScreenshotSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    throttle_scope = "uploads"
