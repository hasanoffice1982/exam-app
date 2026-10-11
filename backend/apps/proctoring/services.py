import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.db.models import F, Q
from django.db.models.functions import Least
from django.utils import timezone

from .authentication import hash_token
from .event_types import EventType
from .models import AuditEntry, Exam, ExamAttempt, ProctorEvent, ProctorScreenshot, Student, StudentToken

logger = logging.getLogger(__name__)

MAX_FAILED_ACTIVATIONS = 5
LOCKOUT_SECONDS = 15 * 60
# No look-alike characters (0/O, 1/l/I) since students must copy this by hand.
PASSWORD_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
PASSWORD_LENGTH = 12


class AuthError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


GLOBAL_FAILURE_CEILING = 50  # per roll number across all addresses: stops a distributed guessing run


def lock_keys(prefix: str, roll_number: str, ip: str = "") -> list[tuple[str, int]]:
    """(cache key, allowed failures). The per-address limit means a classmate cannot lock someone else out by
    failing logins from their own computer; the higher per-roll ceiling still stops guessing from many addresses."""
    return [(f"{prefix}:{roll_number}:{ip}", MAX_FAILED_ACTIVATIONS), (f"{prefix}:{roll_number}", GLOBAL_FAILURE_CEILING)]


def check_lockout(key) -> None:
    pairs = key if isinstance(key, list) else [(key, MAX_FAILED_ACTIVATIONS)]
    if any(cache.get(k, 0) >= limit for k, limit in pairs):
        raise AuthError("Too many failed attempts. Try again in 15 minutes.", 429)


def register_failure(key) -> None:
    for k, _ in key if isinstance(key, list) else [(key, 0)]:
        cache.set(k, cache.get(k, 0) + 1, LOCKOUT_SECONDS)


def clear_failures(key) -> None:
    """A success clears this address's counter (the shared per-roll ceiling decays on its own)."""
    cache.delete((key[0][0] if isinstance(key, list) else key))


def issue_token(student: Student) -> str:
    """Replaces any existing session (one session per student) and returns the raw bearer token."""
    raw = secrets.token_urlsafe(32)
    StudentToken.objects.update_or_create(
        student=student,
        defaults={
            "key_hash": hash_token(raw),
            "issued_at": timezone.now(),
            "expires_at": timezone.now() + timedelta(hours=settings.STUDENT_TOKEN_TTL_HOURS),
            "last_seen_at": None,
        },
    )
    return raw


def authenticate_student(roll_number: str, password: str, ip: str = "") -> Student:
    key = lock_keys("login-fail", roll_number, ip)
    check_lockout(key)
    student = Student.objects.filter(roll_number=roll_number, is_active=True).first()
    if student is not None and not student.is_activated:
        hint = "Use 'First time? Activate account'." if settings.SELF_ACTIVATION else "Ask your teacher for your password."
        raise AuthError(f"Account not activated. {hint}", 401)
    if student is None or not student.check_password(password):
        register_failure(key)
        raise AuthError("Invalid roll number or password.", 401)
    clear_failures(key)
    return student


def new_password() -> str:
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(PASSWORD_LENGTH))


def issue_first_time_passwords(students) -> list[tuple[Student, str]]:
    """Gives each student a fresh random password and returns the plaintexts for ONE printed handout.

    Only hashes are stored, so the sheet cannot be reproduced. Any existing session of a student whose
    password changed is revoked. Used by admins/teachers instead of (or alongside) emailing passwords.
    """
    issued = []
    for student in students:
        password = new_password()
        student.set_password(password)
        student.save(update_fields=["password"])
        issued.append((student, password))
    StudentToken.objects.filter(student_id__in=[s.pk for s, _ in issued]).delete()
    return issued


MIN_PASSWORD_LENGTH = 8


def change_password(student: Student, current_password: str, new_password: str, ip: str = "") -> None:
    """Self-service change. Wrong current passwords count towards the same 5-try lockout as login."""
    key = lock_keys("change-fail", student.roll_number, ip)
    check_lockout(key)
    if not student.check_password(current_password):
        register_failure(key)
        raise AuthError("Your current password is not correct.", 400)
    if len(new_password) < MIN_PASSWORD_LENGTH:
        raise AuthError(f"The new password must be at least {MIN_PASSWORD_LENGTH} characters.", 400)
    if new_password == current_password:
        raise AuthError("The new password must be different from the current one.", 400)
    if new_password.casefold() == student.roll_number.casefold():
        raise AuthError("The new password cannot be your roll number.", 400)
    student.set_password(new_password)
    student.save(update_fields=["password"])
    clear_failures(key)


def mask_email(email: str) -> str:
    """ann.smith@gmail.com -> a***@gmail.com"""
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


def _email_password(student: Student, password: str) -> None:
    send_mail(
        subject="Your ExamProctor password",
        message=(
            f"Hello {student.name},\n\n"
            f"Your ExamProctor account is ready.\n\n"
            f"Roll number: {student.roll_number}\n"
            f"Password:    {password}\n\n"
            "Open the ExamProctor app and log in with these. Keep this password private.\n"
            "If you did not ask for it, ignore this email and tell your teacher."
        ),
        from_email=None,
        recipient_list=[student.email],
        fail_silently=False,
    )


def activate_student(roll_number: str, email: str, ip: str = "") -> str:
    """If roll number and email match a not-yet-activated student, email them a random password.

    The password only ever travels to the registered inbox (it is never returned to the caller), and
    only its hash is stored. If the email cannot be sent the account is left not-activated so the
    student can simply try again. Returns the masked address for display.
    """
    if not settings.SELF_ACTIVATION:
        raise AuthError("Ask your teacher for your password.", 403)
    key = lock_keys("activate-fail", roll_number, ip)
    check_lockout(key)

    student = Student.objects.filter(roll_number=roll_number, is_active=True).first()
    if student is None or not student.email or student.email.lower() != email.strip().lower():
        register_failure(key)
        raise AuthError("Roll number and email do not match our records.", 400)
    if student.is_activated:
        raise AuthError("This account is already activated. Log in with your password, or ask your teacher to reset it.", 409)

    password = new_password()
    student.set_password(password)
    student.save(update_fields=["password"])
    try:
        _email_password(student, password)
    except Exception:
        logger.exception("Could not email the activation password for roll %s", roll_number)
        student.password = ""
        student.save(update_fields=["password"])
        raise AuthError("We could not send the email. Please try again in a minute or tell your teacher.", 503)
    clear_failures(key)
    return mask_email(student.email)


def force_end_attempts(attempts, by_username: str) -> int:
    """Ends in-progress attempts: revokes the sessions, blocks re-entry and logs who did it."""
    rows = list(attempts.filter(status=ExamAttempt.Status.IN_PROGRESS).select_related("student"))
    if not rows:
        return 0
    now = timezone.now()
    ProctorEvent.objects.bulk_create(
        ProctorEvent(student=a.student.label, exam_id=a.exam_id, event_type=EventType.FORCE_ENDED, detail=by_username[:200], timestamp=now)
        for a in rows
    )
    StudentToken.objects.filter(student_id__in=[a.student_id for a in rows]).delete()
    ExamAttempt.objects.filter(pk__in=[a.pk for a in rows]).update(status=ExamAttempt.Status.FORCE_ENDED, ended_at=now)
    return len(rows)


def reset_attempts(attempts) -> int:
    count, _ = ExamAttempt.objects.filter(pk__in=attempts.values("pk")).delete()
    return count


MAX_EXTRA_MINUTES = 480
MAX_GRANT_MINUTES = 180


def add_extra_time(attempts, minutes: int, by_username: str) -> int:
    """Gives students extra time (capped), reopens attempts that ran out of time, and logs who did it.

    Quit and teacher-ended attempts are never reopened by this; use reset for those.
    """
    rows = list(attempts.select_related("student"))
    if not rows:
        return 0
    now = timezone.now()
    pks = [a.pk for a in rows]
    ExamAttempt.objects.filter(pk__in=pks).update(extra_minutes=Least(F("extra_minutes") + minutes, MAX_EXTRA_MINUTES))
    ExamAttempt.objects.filter(pk__in=pks, status=ExamAttempt.Status.COMPLETED).update(
        status=ExamAttempt.Status.IN_PROGRESS, ended_at=None
    )
    ProctorEvent.objects.bulk_create(
        ProctorEvent(
            student=a.student.label, exam_id=a.exam_id, event_type=EventType.TIME_EXTENDED,
            detail=f"+{minutes} min by {by_username}"[:200], timestamp=now,
        )
        for a in rows
    )
    return len(rows)


def advance_to_practical(attempt: ExamAttempt, by: str) -> None:
    """written -> practical for one attempt, logged. Callers have checked the exam has a practical part."""
    updated = ExamAttempt.objects.filter(pk=attempt.pk, stage=ExamAttempt.Stage.WRITTEN).update(stage=ExamAttempt.Stage.PRACTICAL)
    if updated:  # a double click / retry must not log twice
        attempt.stage = ExamAttempt.Stage.PRACTICAL
        ProctorEvent.objects.create(
            student=attempt.student.label, exam_id=attempt.exam_id, event_type=EventType.STAGE_ADVANCED, detail=f"written->practical by {by}"[:200]
        )


def advance_attempts(attempts, by_username: str) -> int:
    """Teacher failsafe: move students still in the written part to the practical part."""
    rows = list(
        attempts.filter(status=ExamAttempt.Status.IN_PROGRESS, stage=ExamAttempt.Stage.WRITTEN, exam__practical_enabled=True)
        .select_related("student")
    )
    for attempt in rows:
        advance_to_practical(attempt, by_username)
    return len(rows)


# ---- archive, evidence retention, deactivation -------------------------------------------------


class RuleError(Exception):
    """A refused action with a message the teacher or admin can act on."""


def _audit(exam: Exam, action: str, by: str, detail: str = "") -> None:
    AuditEntry.objects.create(exam=exam, exam_label=f"{exam.name} ({exam.exam_id})", action=action, detail=detail[:300], performed_by=by)


def archive_exam(exam: Exam, by: str) -> None:
    """Hide a finished exam from students and the default lists.

    While the exam can still be taken, students in progress block it. Once its time is over, attempts that never
    reported an ending (closed laptop, killed app) are completed automatically so they don't block archiving.
    """
    leftovers = ExamAttempt.objects.filter(exam=exam, status=ExamAttempt.Status.IN_PROGRESS)
    count = leftovers.count()
    closed = exam.status == "closed"
    if count and not closed:
        raise RuleError(f"{count} student(s) are still in progress. End or finish their attempts before archiving.")
    if count:
        leftovers.update(status=ExamAttempt.Status.COMPLETED, ended_at=timezone.now())
        _audit(exam, "attempts completed", by, f"{count} attempt(s) never reported an ending; time was over")
    exam.archived = True
    exam.archived_at = timezone.now()
    exam.save(update_fields=["archived", "archived_at"])
    _audit(exam, "archived", by)


def unarchive_exam(exam: Exam, by: str) -> None:
    exam.archived = False
    exam.archived_at = None
    exam.save(update_fields=["archived", "archived_at"])
    _audit(exam, "unarchived", by)


def evidence_summary(exam: Exam) -> tuple[int, int]:
    """(number of images, total bytes) that deleting the exam's screenshots and webcam photos would free."""
    shots = ProctorScreenshot.objects.filter(exam=exam)
    total = 0
    for shot in shots.only("file"):
        try:
            total += shot.file.size
        except (FileNotFoundError, ValueError):
            pass
    return shots.count(), total


def can_delete_evidence(exam: Exam) -> bool:
    """Only once nobody can still add to it: the exam is archived or its time is over."""
    return exam.archived or exam.status == "closed"


def delete_evidence(exam: Exam, by: str, reason: str = "") -> tuple[int, int]:
    """Deletes every screenshot and webcam photo of an exam (rows and files). The event log and marks stay."""
    if not can_delete_evidence(exam):
        raise RuleError("Screenshots can only be deleted after the exam has ended or been archived.")
    count, size = evidence_summary(exam)
    for shot in ProctorScreenshot.objects.filter(exam=exam):
        shot.file.delete(save=False)  # the file; a missing file is fine
        shot.delete()
    _audit(exam, "evidence deleted", by, f"{count} image(s), {size // 1024} KB{'; ' + reason if reason else ''}")
    return count, size


def _ended_before(cutoff):
    return Q(ends_at__lt=cutoff) | Q(archived=True, archived_at__lt=cutoff)


def purge_old_evidence(older_than_days: int, by: str = "purge_evidence", dry_run: bool = False) -> list[tuple[Exam, int]]:
    """Retention sweep: evidence of exams that ended (or were archived) more than N days ago."""
    cutoff = timezone.now() - timedelta(days=older_than_days)
    done = []
    for exam in Exam.objects.filter(_ended_before(cutoff)).distinct():
        count = ProctorScreenshot.objects.filter(exam=exam).count()
        if not count:
            continue
        if not dry_run:
            delete_evidence(exam, by, f"retention {older_than_days} days")
        done.append((exam, count))
    return done


def deactivate_students(students, by: str) -> int:
    """Graduated or finished students: no more logins, sessions revoked. Their records are kept."""
    ids = list(students.filter(is_active=True).values_list("pk", flat=True))
    Student.objects.filter(pk__in=ids).update(is_active=False)
    StudentToken.objects.filter(student_id__in=ids).delete()
    return len(ids)
