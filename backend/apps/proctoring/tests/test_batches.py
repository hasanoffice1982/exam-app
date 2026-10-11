import io

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APITestCase

from apps.proctoring.models import BatchChange, Student

from .helpers import IsolatedMixin, authed_client, make_exam, make_student


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
    def setUp(self):
        super().setUp()
        make_exam("batch81", batch=81)
        make_exam("batch82", batch=82)
        make_exam("everyone")

    def ids(self, client):
        return sorted(e["exam_id"] for e in client.get("/api/exams/").data)

    def test_students_only_see_their_batch_and_open_exams(self):
        c81, _ = authed_client(make_student(roll="1", batch=81))
        c82, _ = authed_client(make_student(roll="2", batch=82))
        self.assertEqual(self.ids(c81), ["batch81", "everyone"])
        self.assertEqual(self.ids(c82), ["batch82", "everyone"])

    def test_student_without_batch_only_sees_open_to_all(self):
        client, _ = authed_client(make_student(roll="3"))
        self.assertEqual(self.ids(client), ["everyone"])

    def test_other_batch_exam_config_is_forbidden(self):
        client, _ = authed_client(make_student(batch=81))
        self.assertEqual(client.get("/api/config/batch81/").status_code, 200)
        self.assertEqual(client.get("/api/config/batch82/").status_code, 403)
        self.assertEqual(client.post("/api/exams/batch82/start/").status_code, 403)

    def test_batch_move_changes_visible_exams(self):
        student = make_student(batch=81)
        client, _ = authed_client(student)
        student = Student.objects.get(pk=student.pk)
        student.batch = 82
        student.save()
        self.assertEqual(self.ids(client), ["batch82", "everyone"])

    def test_exam_list_query_count(self):
        client, _ = authed_client(make_student(batch=81))
        with self.assertNumQueries(2):
            client.get("/api/exams/")
