import io

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APITestCase

from apps.proctoring.models import BatchChange, Exam, Student

from .helpers import IsolatedMixin, authed_client, make_exam, make_student
from .test_dashboard import DashboardBase


class BatchRuleTests(TestCase):
    def move(self, student_id: int, batch):
        student = Student.objects.get(pk=student_id)
        student.batch = batch
        student.save()
        return student

    def test_forward_moves_are_allowed(self):
        s = make_student(batch=81)
        self.move(s.pk, 82)
        self.move(s.pk, 85)
        self.assertEqual(Student.objects.get(pk=s.pk).batch, 85)

    def test_backward_move_is_rejected(self):
        s = make_student(batch=95)
        with self.assertRaises(ValidationError):
            self.move(s.pk, 94)
        self.assertEqual(Student.objects.get(pk=s.pk).batch, 95)

    def test_clearing_a_batch_counts_as_backward(self):
        s = make_student(batch=81)
        with self.assertRaises(ValidationError):
            self.move(s.pk, None)

    def test_same_batch_is_a_noop_not_an_error(self):
        s = make_student(batch=81)
        self.move(s.pk, 81)
        self.assertFalse(BatchChange.objects.exists())

    def test_first_assignment_and_new_students_are_free(self):
        unassigned = make_student(roll="1")
        self.move(unassigned.pk, 90)
        make_student(roll="2", batch=3)  # any starting batch
        self.assertEqual(Student.objects.get(pk=unassigned.pk).batch, 90)

    def test_moves_are_audited(self):
        s = make_student(batch=81)
        student = Student.objects.get(pk=s.pk)
        student.batch = 83
        student._changed_by = "registrar"
        student.save()
        change = BatchChange.objects.get()
        self.assertEqual((change.from_batch, change.to_batch, change.changed_by), (81, 83, "registrar"))

    def test_consecutive_moves_on_one_instance(self):
        s = make_student(batch=81)
        s.batch = 82
        s.save()
        s.batch = 85
        s.save()
        s.batch = 84
        with self.assertRaises(ValidationError):
            s.save()
        self.assertEqual(BatchChange.objects.count(), 2)

    def test_form_validation_message(self):
        s = Student.objects.get(pk=make_student(batch=95).pk)
        s.batch = 94
        with self.assertRaisesMessage(ValidationError, "forward"):
            s.full_clean()


class AdminBatchTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser("root", "r@example.com", "pw")
        self.client.force_login(self.admin)
        self.student = make_student(batch=95)

    def post_batch(self, batch):
        return self.client.post(
            f"/admin/proctoring/student/{self.student.pk}/change/",
            {"roll_number": "1", "name": "Ann", "email": "ann@example.com", "batch": batch, "is_active": "on",
             "batch_changes-TOTAL_FORMS": 0, "batch_changes-INITIAL_FORMS": 0},
        )

    def test_admin_rejects_backward_move(self):
        res = self.post_batch(94)
        self.assertEqual(res.status_code, 200)  # form redisplayed with an error
        self.assertContains(res, "Batch can only move forward")
        self.student.refresh_from_db()
        self.assertEqual(self.student.batch, 95)

    def test_admin_accepts_forward_move_and_records_who(self):
        res = self.post_batch(96)
        self.assertEqual(res.status_code, 302)
        self.student.refresh_from_db()
        self.assertEqual(self.student.batch, 96)
        self.assertEqual(BatchChange.objects.get().changed_by, "root")


class CsvImportTests(TestCase):
    def run_csv(self, text):
        import os
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write(text)
        out, err = io.StringIO(), io.StringIO()
        try:
            call_command("import_students", f.name, stdout=out, stderr=err)
        finally:
            os.unlink(f.name)
        return out.getvalue(), err.getvalue()

    def test_import_sets_batch_and_skips_backward_rows(self):
        self.run_csv("roll_number,name,email,batch\n1,Ann,a@x.com,81\n2,Bob,b@x.com,90\n")
        out, err = self.run_csv("roll_number,name,email,batch\n1,Ann,a@x.com,85\n2,Bob,b@x.com,89\n3,Cy,c@x.com,70\n")
        self.assertEqual(Student.objects.get(roll_number="1").batch, 85)
        self.assertEqual(Student.objects.get(roll_number="2").batch, 90)  # not moved back
        self.assertEqual(Student.objects.get(roll_number="3").batch, 70)
        self.assertIn("SKIPPED 2", err)

    def test_import_without_batch_column_keeps_existing_batch(self):
        self.run_csv("roll_number,name,email,batch\n1,Ann,a@x.com,81\n")
        self.run_csv("roll_number,name,email\n1,Ann B,a@x.com\n")
        student = Student.objects.get(roll_number="1")
        self.assertEqual((student.name, student.batch), ("Ann B", 81))


class ExamEligibilityTests(IsolatedMixin, APITestCase):
    """Every exam belongs to exactly one batch; nobody else sees it, and there is no "all batches"."""

    def setUp(self):
        super().setUp()
        make_exam("batch81", batch=81)
        make_exam("batch82", batch=82)
        make_exam("nobatch", batch=None)  # legacy row: not assigned yet

    def ids(self, client):
        return sorted(e["exam_id"] for e in client.get("/api/exams/").data)

    def test_students_only_see_their_own_batchs_exams(self):
        c81, _ = authed_client(make_student(roll="1", batch=81))
        c82, _ = authed_client(make_student(roll="2", batch=82))
        self.assertEqual(self.ids(c81), ["batch81"])
        self.assertEqual(self.ids(c82), ["batch82"])

    def test_exams_without_a_batch_are_invisible_to_everyone(self):
        for roll, batch in (("1", 81), ("2", 82), ("3", None)):
            client, _ = authed_client(make_student(roll=roll, batch=batch))
            self.assertNotIn("nobatch", self.ids(client))

    def test_student_without_a_batch_sees_nothing(self):
        client, _ = authed_client(make_student(roll="3", batch=None))
        self.assertEqual(self.ids(client), [])

    def test_other_batch_and_unassigned_exams_are_forbidden(self):
        client, _ = authed_client(make_student(batch=81))
        self.assertEqual(client.get("/api/config/batch81/").status_code, 200)
        for other in ("batch82", "nobatch"):
            self.assertEqual(client.get(f"/api/config/{other}/").status_code, 403, other)
            self.assertEqual(client.post(f"/api/exams/{other}/start/").status_code, 403, other)
            self.assertEqual(client.post(f"/api/exams/{other}/advance/").status_code, 403, other)

    def test_batch_move_changes_visible_exams(self):
        student = make_student(batch=81)
        client, _ = authed_client(student)
        student = Student.objects.get(pk=student.pk)
        student.batch = 82
        student.save()
        self.assertEqual(self.ids(client), ["batch82"])

    def test_exam_list_query_count(self):
        client, _ = authed_client(make_student(batch=81))
        with self.assertNumQueries(2):
            client.get("/api/exams/")


class ExamBatchAdminTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser("root", "r@example.com", "pw")
        self.client.force_login(self.admin)

    def add(self, **extra):
        data = {"exam_id": "new-exam", "name": "New", "form_url": "https://example.com/form", "written_enabled": "on",
                "practical_screenshot_seconds": 60, "webcam_interval_seconds": 180, "grace_seconds": 3, "monitoring_enabled": "on",
                **extra}
        return self.client.post("/admin/proctoring/exam/add/", data)

    def test_admin_refuses_an_exam_without_a_batch(self):
        res = self.add()
        self.assertEqual(res.status_code, 200)  # form redisplayed with an error
        self.assertContains(res, "This field is required")
        self.assertFalse(Exam.objects.filter(exam_id="new-exam").exists())

    def test_admin_accepts_an_exam_with_a_batch(self):
        self.assertEqual(self.add(batch=81).status_code, 302)
        self.assertEqual(Exam.objects.get(exam_id="new-exam").batch, 81)


class TeacherExamListGroupingTests(DashboardBase):
    def test_exams_are_grouped_by_batch_in_order(self):
        from apps.proctoring.models import Exam as ExamModel

        ExamModel.objects.filter(pk=self.math.pk).update(batch=82)
        three = make_exam("math-201", name="Math 201", batch=81)
        three.teachers.add(get_user_model().objects.get(username="mathteacher"))
        html = self.as_user("mathteacher").get("/teacher/").content.decode()
        self.assertLess(html.index("Batch 81"), html.index("Batch 82"))
        self.assertLess(html.index("Math 201"), html.index("Mathematics"))  # 81 group before the 82 group
        self.assertNotIn("All batches", html)

    def test_exams_without_a_batch_get_a_warning_group_first(self):
        from apps.proctoring.models import Exam as ExamModel

        ExamModel.objects.filter(pk=self.math.pk).update(batch=None)
        html = self.as_user("mathteacher").get("/teacher/").content.decode()
        self.assertIn("No batch set", html)
        self.assertIn("students cannot see these", html)

    def test_a_teacher_only_sees_their_own_batches_exams(self):
        html = self.as_user("physteacher").get("/teacher/").content.decode()
        self.assertIn("physics-101", html)
        self.assertNotIn("math-101", html)
