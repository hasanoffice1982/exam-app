from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from apps.proctoring import services
from apps.proctoring.models import Exam, ExamAttempt, ProctorEvent, StudentToken

from .helpers import authed_client, make_exam, make_student


class TeacherAdminTests(TestCase):
    """Two subject teachers: each only reaches their own exam's data."""

    def setUp(self):
        self.math = make_exam("math-101", name="Mathematics")
        self.phys = make_exam("physics-101", name="Physics")
        out = StringIO()
        call_command("create_teacher", "mathteacher", "--exams", "math-101", "--password", "pw-math", stdout=out)
        call_command("create_teacher", "physteacher", "--exams", "physics-101", "--password", "pw-phys", stdout=out)
        self.root = get_user_model().objects.create_superuser("root", "r@example.com", "pw-root")

        self.ann = make_student(roll="1", name="Ann", batch=81)
        self.bob = make_student(roll="2", name="Bob", email="b@example.com", batch=81)
        self.ann_attempt = ExamAttempt.objects.create(student=self.ann, exam=self.math)
        self.bob_attempt = ExamAttempt.objects.create(student=self.bob, exam=self.phys)
        ProctorEvent.objects.create(student="Ann (1)", exam=self.math, event_type="tab_switch")
        ProctorEvent.objects.create(student="Bob (2)", exam=self.phys, event_type="tab_switch")

    def login(self, username, password):
        self.client.logout()
        self.assertTrue(self.client.login(username=username, password=password))

    def test_teacher_sees_only_their_exam(self):
        self.login("mathteacher", "pw-math")
        res = self.client.get("/admin/proctoring/exam/")
        self.assertContains(res, "math-101")
        self.assertNotContains(res, "physics-101")

    def test_teacher_sees_only_their_attempts_and_events(self):
        self.login("mathteacher", "pw-math")
        attempts = self.client.get("/admin/proctoring/examattempt/")
        self.assertContains(attempts, "Ann")
        self.assertNotContains(attempts, "Bob")
        events = self.client.get("/admin/proctoring/proctorevent/")
        self.assertContains(events, "Ann (1)")
        self.assertNotContains(events, "Bob (2)")

    def test_exam_filter_lists_only_own_exams(self):
        self.login("mathteacher", "pw-math")
        res = self.client.get("/admin/proctoring/proctorevent/")
        self.assertContains(res, "Mathematics")
        self.assertNotContains(res, "Physics")

    def test_other_teachers_objects_404(self):
        self.login("mathteacher", "pw-math")
        self.assertEqual(self.client.get(f"/admin/proctoring/examattempt/{self.bob_attempt.pk}/change/").status_code, 302)
        self.assertEqual(self.client.get(f"/admin/proctoring/exam/{self.phys.pk}/change/").status_code, 302)
        self.assertEqual(self.client.get(f"/admin/proctoring/exam/{self.math.pk}/change/").status_code, 200)

    def test_teacher_cannot_touch_students_sessions_or_other_models(self):
        self.login("mathteacher", "pw-math")
        for url in ("student", "studenttoken", "batchchange"):
            self.assertIn(self.client.get(f"/admin/proctoring/{url}/").status_code, (403, 404), url)
        self.assertEqual(self.client.get("/admin/auth/user/").status_code, 403)

    def test_teacher_cannot_add_or_delete_exams(self):
        self.login("mathteacher", "pw-math")
        self.assertEqual(self.client.get("/admin/proctoring/exam/add/").status_code, 403)
        self.assertEqual(self.client.get(f"/admin/proctoring/exam/{self.math.pk}/delete/").status_code, 403)

    def test_teacher_can_edit_schedule_but_not_assignment_fields(self):
        self.login("mathteacher", "pw-math")
        res = self.client.get(f"/admin/proctoring/exam/{self.math.pk}/change/")
        self.assertContains(res, 'name="monitoring_enabled"')
        self.assertContains(res, 'name="grace_seconds"')
        for locked in ("batch", "teachers", "exam_id"):
            self.assertNotContains(res, f'name="{locked}"')

    def run_action(self, action, attempt):
        return self.client.post(
            "/admin/proctoring/examattempt/",
            {"action": action, "_selected_action": [attempt.pk]},
            follow=True,
        )

    def test_force_end_kicks_student_and_blocks_reentry(self):
        client, _ = authed_client(self.ann)
        self.login("mathteacher", "pw-math")
        self.run_action("force_end", self.ann_attempt)

        self.ann_attempt.refresh_from_db()
        self.assertEqual(self.ann_attempt.status, "force_ended")
        self.assertIsNotNone(self.ann_attempt.ended_at)
        self.assertEqual(client.get("/api/exams/").status_code, 401)  # session revoked
        event = ProctorEvent.objects.get(event_type="force_ended")
        self.assertEqual((event.student, event.detail), ("Ann (1)", "mathteacher"))

        new_client, _ = authed_client(self.ann)
        res = new_client.post("/api/exams/math-101/start/")
        self.assertEqual(res.status_code, 403)
        self.assertIn("teacher ended", res.data["detail"])

    def test_teacher_cannot_force_end_another_subjects_attempt(self):
        client, _ = authed_client(self.bob)
        self.login("mathteacher", "pw-math")
        self.run_action("force_end", self.bob_attempt)
        self.bob_attempt.refresh_from_db()
        self.assertEqual(self.bob_attempt.status, "in_progress")
        self.assertEqual(client.get("/api/exams/").status_code, 200)

    def test_reset_attempt_lets_student_start_again(self):
        services.issue_token(self.ann)
        self.login("mathteacher", "pw-math")
        self.run_action("force_end", self.ann_attempt)
        self.run_action("reset_attempt", self.ann_attempt)
        self.assertFalse(ExamAttempt.objects.filter(pk=self.ann_attempt.pk).exists())
        client, _ = authed_client(self.ann)
        self.assertEqual(client.post("/api/exams/math-101/start/").status_code, 200)

    def test_superuser_sees_everything_and_can_assign_teachers(self):
        self.login("root", "pw-root")
        self.assertContains(self.client.get("/admin/proctoring/exam/"), "physics-101")
        attempts = self.client.get("/admin/proctoring/examattempt/")
        self.assertContains(attempts, "Ann")
        self.assertContains(attempts, "Bob")
        self.assertContains(self.client.get(f"/admin/proctoring/exam/{self.math.pk}/change/"), 'name="teachers"')

    def test_create_teacher_rejects_unknown_exam_and_is_idempotent(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("create_teacher", "x", "--exams", "nope", stdout=StringIO())
        call_command("create_teacher", "mathteacher", "--exams", "physics-101", stdout=StringIO())
        teacher = get_user_model().objects.get(username="mathteacher")
        self.assertEqual(sorted(Exam.objects.filter(teachers=teacher).values_list("exam_id", flat=True)), ["math-101", "physics-101"])
        self.assertFalse(teacher.is_superuser)
