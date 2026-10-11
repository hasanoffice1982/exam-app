import csv
import io
from datetime import timedelta

from django.db.models import Count, Max
from django.utils import timezone

from . import scoring
from .models import Exam, ExamAttempt, ProctorEvent, ProctorScreenshot

ONLINE_WINDOW = timedelta(seconds=90)  # three missed 30 s heartbeats


def scoped_exams(user):
    return Exam.objects.all() if user.is_superuser else Exam.objects.filter(teachers=user)


def _state(attempt: ExamAttempt, now) -> str:
    if attempt.status != ExamAttempt.Status.IN_PROGRESS:
        return "ended"
    token = getattr(attempt.student, "token", None)
    seen = token.last_seen_at if token else None
    return "online" if seen and now - seen <= ONLINE_WINDOW else "offline"


def live_rows(exam: Exam) -> list[dict]:
    """One row per student attempt. Constant number of queries however many students there are."""
    now = timezone.now()
    attempts = list(ExamAttempt.objects.filter(exam=exam).select_related("student", "student__token"))
    counts: dict[str, dict[str, int]] = {}
    last_event: dict[str, object] = {}
    grouped = ProctorEvent.objects.filter(exam=exam).values("student", "event_type").annotate(n=Count("id"), last=Max("timestamp"))
    for row in grouped:
        counts.setdefault(row["student"], {})[row["event_type"]] = row["n"]
        if row["student"] not in last_event or row["last"] > last_event[row["student"]]:
            last_event[row["student"]] = row["last"]

    rows = []
    for attempt in attempts:
        student = attempt.student
        student_counts = counts.get(student.label, {})
        total, flag = scoring.summarize(student_counts)
        token = getattr(student, "token", None)
        rows.append(
            {
                "attempt_id": attempt.pk,
                "roll_number": student.roll_number,
                "name": student.name,
                "batch": student.batch,
                "status": attempt.status,
                "stage": attempt.stage,
                "stage_label": attempt.get_stage_display(),
                "can_advance": exam.practical_enabled and attempt.stage == ExamAttempt.Stage.WRITTEN and attempt.status == ExamAttempt.Status.IN_PROGRESS,
                "status_label": attempt.get_status_display(),
                "state": _state(attempt, now),
                "started_at": attempt.started_at.isoformat(),
                "last_seen": token.last_seen_at.isoformat() if token and token.last_seen_at else None,
                "last_event_at": last_event[student.label].isoformat() if student.label in last_event else None,
                "tab_switches": student_counts.get("tab_switch", 0),
                "restarts": student_counts.get("exam_resumed", 0),
                "extra_minutes": attempt.extra_minutes,
                "score": total,
                "flag": flag,
                "counts": student_counts,
            }
        )
    rows.sort(key=lambda r: (-r["score"], r["roll_number"]))
    return rows


def timeline(exam: Exam, attempt: ExamAttempt) -> dict:
    """Everything the student timeline page shows: merged items plus the student's score and flag."""
    label = attempt.student.label
    items = []
    counts: dict[str, int] = {}
    for e in ProctorEvent.objects.filter(exam=exam, student=label).only("event_type", "detail", "timestamp"):
        counts[e.event_type] = counts.get(e.event_type, 0) + 1
        items.append(
            {
                "kind": "event",
                "time": e.timestamp,
                "type": e.event_type,
                "label": scoring.label(e.event_type),
                "detail": e.detail,
                "weight": scoring.weight(e.event_type),
            }
        )
    for s in ProctorScreenshot.objects.filter(exam=exam, student=label).only("timestamp", "kind"):
        items.append({"kind": "screenshot", "time": s.timestamp, "id": s.pk, "shot_label": s.get_kind_display()})
    items.sort(key=lambda i: i["time"])
    total, flag = scoring.summarize(counts)
    return {"items": items, "score": total, "flag": flag}


def safe_cell(value) -> str:
    """Neutralise spreadsheet formula injection (=, +, -, @ at the start of a cell)."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def summary_csv(exam: Exam) -> str:
    rows = live_rows(exam)
    types = sorted({t for r in rows for t in r["counts"]})
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["roll_number", "name", "batch", "attempt_status", "started_at", "last_seen", "score", "flag", *types])
    for r in rows:
        writer.writerow(
            [safe_cell(v) for v in (r["roll_number"], r["name"], r["batch"], r["status"], r["started_at"], r["last_seen"], r["score"], r["flag"])]
            + [r["counts"].get(t, 0) for t in types]
        )
    return out.getvalue()


def events_csv(exam: Exam) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["timestamp", "student", "event_type", "detail", "weight"])
    for e in ProctorEvent.objects.filter(exam=exam).order_by("timestamp").only("student", "event_type", "detail", "timestamp"):
        writer.writerow([e.timestamp.isoformat(), safe_cell(e.student), e.event_type, safe_cell(e.detail), scoring.weight(e.event_type)])
    return out.getvalue()


def marks_csv(rows: list[dict]) -> str:
    from . import marking

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(marking.MARK_COLUMNS)
    for r in rows:
        writer.writerow([safe_cell(r[c]) for c in marking.MARK_COLUMNS])
    return out.getvalue()
