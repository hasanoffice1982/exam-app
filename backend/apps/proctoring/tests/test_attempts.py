import uuid
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITransactionTestCase

from apps.proctoring.models import ExamAttempt

from .helpers import IsolatedMixin, authed_client, make_exam, make_student


class AttemptTests(IsolatedMixin, APITransactionTestCase):
    def setUp(self):
        super().setUp()
        self.exam = make_exam()
        self.student = make_student()
        self.client, _ = authed_client(self.student)

    def start(self, exam_id="math-101"):
        return self.client.post(f"/api/exams/{exam_id}/start/")

    def event(self, event_type):
        return self.client.post(
            "/api/events/", {"exam_id": "math-101", "event_type": event_type, "client_id": str(uuid.uuid4())}, format="json"
        )

    def test_start_creates_attempt_and_returns_config(self):
        res = self.start()
        self.assertEqual(res.status_code, 200)
        self.assertIn("form_url", res.data)
        attempt = ExamAttempt.objects.get()
        self.assertEqual(attempt.status, "in_progress")

    def test_start_query_counts(self):
        with self.assertNumQueries(4):  # auth, exam, attempt lookup, attempt insert
            self.start()
        with self.assertNumQueries(4):  # resume: auth, exam, attempt lookup, resume event
            self.start()

    def test_resume_after_crash_is_allowed(self):
        self.start()
        self.assertEqual(self.start().status_code, 200)
        self.assertEqual(ExamAttempt.objects.count(), 1)

    def test_resume_leaves_a_trace_but_first_start_does_not(self):
        from apps.proctoring.models import ProctorEvent

        self.start()
        self.assertFalse(ProctorEvent.objects.filter(event_type="exam_resumed").exists())
        self.start()
        self.start()
        events = ProctorEvent.objects.filter(event_type="exam_resumed")
        self.assertEqual(events.count(), 2)
        self.assertEqual(events.first().student, "Ann (1)")

    def test_closed_and_upcoming_exams_cannot_be_started(self):
        self.exam.ends_at = timezone.now() - timedelta(minutes=1)
        self.exam.save()
        res = self.start()
        self.assertEqual((res.status_code, res.data["detail"]), (403, "This exam has ended."))
        self.exam.ends_at, self.exam.starts_at = None, timezone.now() + timedelta(hours=1)
        self.exam.save()
        self.assertEqual(self.start().data["detail"], "This exam has not started yet.")
        self.assertFalse(ExamAttempt.objects.exists())

    def test_quit_event_ends_the_attempt_for_good(self):
        self.start()
        self.assertEqual(self.event("exam_quit").status_code, 201)
        self.assertEqual(ExamAttempt.objects.get().status, "quit")
        res = self.start()
        self.assertEqual(res.status_code, 403)
        self.assertIn("cannot re-enter", res.data["detail"])

    def test_time_up_event_completes_the_attempt(self):
        self.start()
        self.event("time_up")
        self.assertEqual(ExamAttempt.objects.get().status, "completed")

    def test_ordinary_events_do_not_touch_the_attempt_or_cost_extra_queries(self):
        self.start()
        with self.assertNumQueries(3):
            self.event("tab_switch")
        self.assertEqual(ExamAttempt.objects.get().status, "in_progress")

    def test_retried_quit_event_is_idempotent(self):
        self.start()
        cid = str(uuid.uuid4())
        body = {"exam_id": "math-101", "event_type": "exam_quit", "client_id": cid}
        self.assertEqual(self.client.post("/api/events/", body, format="json").status_code, 201)
        self.assertEqual(self.client.post("/api/events/", body, format="json").status_code, 200)
        self.assertEqual(ExamAttempt.objects.get().status, "quit")

    def test_attempts_are_per_exam(self):
        make_exam("physics-101")
        self.start()
        self.event("exam_quit")
        self.assertEqual(self.start("physics-101").status_code, 200)
