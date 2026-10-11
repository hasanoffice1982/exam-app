from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITransactionTestCase

from apps.proctoring import services
from apps.proctoring.models import ExamAttempt, ProctorEvent

from .helpers import IsolatedMixin, authed_client, make_exam, make_student
from .test_dashboard import DashboardBase


class ExtraTimeApiTests(IsolatedMixin, APITransactionTestCase):
    def setUp(self):
        super().setUp()
        self.exam = make_exam(starts_at=timezone.now() - timedelta(hours=2), ends_at=timezone.now() + timedelta(minutes=30))
        self.ann = make_student(roll="1", name="Ann")
        self.bob = make_student(roll="2", name="Bob", email="b@example.com")
        self.ann_client, _ = authed_client(self.ann)
        self.bob_client, _ = authed_client(self.bob)
        self.ann_client.post("/api/exams/math-101/start/")
        self.bob_client.post("/api/exams/math-101/start/")

    def give(self, student, minutes):
        attempts = ExamAttempt.objects.filter(student=student)
        return services.add_extra_time(attempts, minutes, "teacher")

    def end_exam_now(self):
        self.exam.ends_at = timezone.now() - timedelta(minutes=1)
        self.exam.save()

    def test_personal_deadline_is_returned_by_config_and_start(self):
        self.give(self.ann, 15)
        official = self.exam.ends_at
        ann = self.ann_client.get("/api/config/math-101/").data["ends_at"]
        bob = self.bob_client.get("/api/config/math-101/").data["ends_at"]
        self.assertAlmostEqual(
            timezone.datetime.fromisoformat(ann.replace("Z", "+00:00")).timestamp(), (official + timedelta(minutes=15)).timestamp(), delta=1
        )
        self.assertAlmostEqual(
            timezone.datetime.fromisoformat(bob.replace("Z", "+00:00")).timestamp(), official.timestamp(), delta=1
        )
        start = self.ann_client.post("/api/exams/math-101/start/").data["ends_at"]
        self.assertEqual(start, ann)

    def test_student_with_extra_time_can_resume_after_the_official_end(self):
        self.give(self.ann, 10)
        self.end_exam_now()
        self.assertEqual(self.ann_client.get("/api/config/math-101/").data["status"], "open")
        self.assertEqual(self.ann_client.post("/api/exams/math-101/start/").status_code, 200)
        res = self.bob_client.post("/api/exams/math-101/start/")
        self.assertEqual((res.status_code, res.data["detail"]), (403, "This exam has ended."))
        self.assertEqual(self.bob_client.get("/api/config/math-101/").data["status"], "closed")

    def test_extra_time_expires_too(self):
        self.give(self.ann, 1)
        self.exam.ends_at = timezone.now() - timedelta(minutes=2)
        self.exam.save()
        self.assertEqual(self.ann_client.post("/api/exams/math-101/start/").status_code, 403)

    def test_extra_time_adds_up_and_is_capped(self):
        self.give(self.ann, 100)
        self.give(self.ann, 100)
        self.assertEqual(ExamAttempt.objects.get(student=self.ann).extra_minutes, 200)
        for _ in range(5):
            self.give(self.ann, 180)
        self.assertEqual(ExamAttempt.objects.get(student=self.ann).extra_minutes, services.MAX_EXTRA_MINUTES)

    def test_time_up_attempt_is_reopened_but_quit_and_force_ended_are_not(self):
        ExamAttempt.objects.filter(student=self.ann).update(status="completed", ended_at=timezone.now())
        ExamAttempt.objects.filter(student=self.bob).update(status="quit", ended_at=timezone.now())
        self.give(self.ann, 10)
        self.give(self.bob, 10)
        ann, bob = ExamAttempt.objects.get(student=self.ann), ExamAttempt.objects.get(student=self.bob)
        self.assertEqual((ann.status, ann.ended_at), ("in_progress", None))
        self.assertEqual(bob.status, "quit")

    def test_the_grant_is_logged_with_who_gave_it(self):
        self.give(self.ann, 10)
        event = ProctorEvent.objects.get(event_type="time_extended")
        self.assertEqual((event.student, event.detail), ("Ann (1)", "+10 min by teacher"))

    def test_config_costs_the_same_for_timed_and_untimed_exams(self):
        with self.assertNumQueries(3):  # auth, exam, the student's attempt (stage + extra time)
            self.ann_client.get("/api/config/math-101/")
        self.exam.ends_at = None
        self.exam.save()
        with self.assertNumQueries(3):
            self.ann_client.get("/api/config/math-101/")


class ExtraTimeDashboardTests(DashboardBase):
    def url(self, exam="math-101", pk=None):
        return f"/teacher/exams/{exam}/attempts/{pk or self.ann_attempt.pk}/extra-time/"

    def test_teacher_gives_extra_time(self):
        res = self.as_user("mathteacher").post(self.url(), {"minutes": "10"})
        self.assertEqual(res.json(), {"ok": True, "changed": 1})
        self.ann_attempt.refresh_from_db()
        self.assertEqual(self.ann_attempt.extra_minutes, 10)
        self.assertEqual(ProctorEvent.objects.get(event_type="time_extended").detail, "+10 min by mathteacher")

    def test_minutes_are_validated(self):
        client = self.as_user("mathteacher")
        for bad in ("", "abc", "0", "-5", "181", "1.5"):
            self.assertEqual(client.post(self.url(), {"minutes": bad}).status_code, 400, bad)
        self.ann_attempt.refresh_from_db()
        self.assertEqual(self.ann_attempt.extra_minutes, 0)

    def test_other_subjects_teacher_cannot(self):
        self.assertEqual(self.as_user("physteacher").post(self.url(), {"minutes": "10"}).status_code, 404)
        self.assertEqual(self.as_user("mathteacher").post(self.url(pk=self.bob_attempt.pk), {"minutes": "10"}).status_code, 404)
        self.bob_attempt.refresh_from_db()
        self.assertEqual(self.bob_attempt.extra_minutes, 0)

    def test_get_anonymous_and_csrf_are_enforced(self):
        from django.test import Client

        self.assertEqual(self.as_user("mathteacher").get(self.url()).status_code, 405)
        self.assertEqual(Client().post(self.url(), {"minutes": "10"}).status_code, 302)
        strict = Client(enforce_csrf_checks=True)
        strict.login(username="mathteacher", password="pw")
        self.assertEqual(strict.post(self.url(), {"minutes": "10"}).status_code, 403)

    def test_monitor_rows_show_restarts_and_extra_time(self):
        for _ in range(2):
            self.event(self.ann, self.math, "exam_resumed")
        services.add_extra_time(ExamAttempt.objects.filter(pk=self.ann_attempt.pk), 5, "t")
        row = self.live(self.as_user("mathteacher"))[0]
        self.assertEqual((row["restarts"], row["extra_minutes"], row["score"]), (2, 5, 0))  # restarts alone don't flag

    def test_timeline_labels_the_new_events(self):
        self.event(self.ann, self.math, "exam_resumed")
        self.event(self.ann, self.math, "time_extended", "+10 min by t")
        html = self.as_user("mathteacher").get("/teacher/exams/math-101/students/1/").content.decode()
        self.assertIn("Reopened the exam", html)
        self.assertIn("Teacher gave extra time", html)
