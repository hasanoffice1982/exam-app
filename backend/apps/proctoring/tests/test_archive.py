import os
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.proctoring import services
from apps.proctoring.models import AuditEntry, Exam, ExamAttempt, ProctorEvent, ProctorScreenshot, Student, StudentToken

from .helpers import PASSWORD, IsolatedMixin, authed_client, make_exam, make_student
from .test_dashboard import DashboardBase


def media_files(root):
    return [f for _, _, files in os.walk(root) for f in files]


class ArchiveApiTests(IsolatedMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.exam = make_exam("math-101", archived=True, archived_at=timezone.now())
        make_exam("physics-101")
        self.client, _ = authed_client(make_student(batch=81))

    def test_archived_exams_are_not_listed(self):
        self.assertEqual([e["exam_id"] for e in self.client.get("/api/exams/").data], ["physics-101"])

    def test_archived_exams_cannot_be_opened_started_or_advanced(self):
        self.assertEqual(self.client.get("/api/config/math-101/").status_code, 403)
        for url in ("start", "advance"):
            res = self.client.post(f"/api/exams/math-101/{url}/")
            self.assertEqual((res.status_code, res.data["detail"]), (403, "This exam has been archived."))
        self.assertFalse(ExamAttempt.objects.exists())

    def test_the_batch_message_wins_for_students_of_another_batch(self):
        other, _ = authed_client(make_student(roll="2", name="Bob", email="b@x.com", batch=82))
        self.assertEqual(other.post("/api/exams/math-101/start/").data["detail"], "This exam is not assigned to your batch.")

    def test_unarchiving_restores_access(self):
        services.unarchive_exam(self.exam, "t")
        self.assertEqual(self.client.post("/api/exams/math-101/start/").status_code, 200)


class TeacherArchiveTests(DashboardBase):
    def post(self, client, action, exam="math-101", **extra):
        return client.post(f"/teacher/exams/{exam}/{action}/", follow=True, **extra)

    def test_a_teacher_archives_a_finished_exam_and_it_is_logged(self):
        ExamAttempt.objects.filter(pk=self.ann_attempt.pk).update(status="completed")
        res = self.post(self.as_user("mathteacher"), "archive")
        self.math.refresh_from_db()
        self.assertTrue(self.math.archived)
        self.assertIsNotNone(self.math.archived_at)
        self.assertContains(res, "is archived")
        entry = AuditEntry.objects.get()
        self.assertEqual((entry.action, entry.performed_by, entry.exam_id), ("archived", "mathteacher", self.math.pk))

    def test_archiving_is_refused_while_students_are_still_in_progress(self):
        res = self.post(self.as_user("mathteacher"), "archive")  # Ann is in progress
        self.assertContains(res, "still in progress")
        self.math.refresh_from_db()
        self.assertFalse(self.math.archived)
        self.assertFalse(AuditEntry.objects.exists())

    def test_unarchive(self):
        ExamAttempt.objects.filter(pk=self.ann_attempt.pk).update(status="completed")
        client = self.as_user("mathteacher")
        self.post(client, "archive")
        res = self.post(client, "unarchive")
        self.math.refresh_from_db()
        self.assertFalse(self.math.archived)
        self.assertContains(res, "active again")
        self.assertEqual(list(AuditEntry.objects.values_list("action", flat=True).order_by("at")), ["archived", "unarchived"])

    def test_scoping_methods_csrf_and_login(self):
        url = "/teacher/exams/math-101/archive/"
        self.assertEqual(self.as_user("physteacher").post(url).status_code, 404)
        self.assertEqual(self.as_user("mathteacher").get(url).status_code, 405)
        self.assertEqual(Client().post(url).status_code, 302)
        strict = Client(enforce_csrf_checks=True)
        strict.login(username="mathteacher", password="pw")
        self.assertEqual(strict.post(url).status_code, 403)
        self.math.refresh_from_db()
        self.assertFalse(self.math.archived)

    def test_archived_exams_are_hidden_from_the_default_list_but_can_be_shown(self):
        Exam.objects.filter(pk=self.math.pk).update(archived=True, archived_at=timezone.now())
        client = self.as_user("mathteacher")
        default = client.get("/teacher/")
        self.assertNotContains(default, "Mathematics")  # DashboardBase names the exam "Mathematics"
        self.assertContains(default, "Show 1 archived exam")
        shown = client.get("/teacher/?archived=1")
        self.assertContains(shown, "Mathematics")
        self.assertContains(shown, "hidden from students")
        self.assertContains(shown, "Hide archived exams")

    def test_an_archived_exam_stays_fully_readable_for_marking(self):
        self.event(self.ann, self.math, "tab_switch")
        Exam.objects.filter(pk=self.math.pk).update(archived=True, archived_at=timezone.now())
        client = self.as_user("mathteacher")
        for url in ("/teacher/exams/math-101/", "/teacher/exams/math-101/live.json", "/teacher/exams/math-101/summary.csv",
                    "/teacher/exams/math-101/events.csv", "/teacher/exams/math-101/students/1/", "/teacher/exams/math-101/marks/"):
            self.assertEqual(client.get(url).status_code, 200, url)
        page = client.get("/teacher/exams/math-101/").content.decode()
        self.assertIn("archived", page)
        self.assertIn("Unarchive", page)

    def test_the_super_admin_can_archive_from_the_admin(self):
        ExamAttempt.objects.filter(pk=self.ann_attempt.pk).update(status="completed")
        client = Client()
        client.login(username="root", password="pw")
        client.post("/admin/proctoring/exam/", {"action": "archive_selected", "_selected_action": [self.math.pk]}, follow=True)
        self.math.refresh_from_db()
        self.assertTrue(self.math.archived)
        self.assertEqual(AuditEntry.objects.get().performed_by, "root")


class EvidenceDeletionTests(DashboardBase):
    url = "/teacher/exams/math-101/delete-evidence/"

    def setUp(self):
        super().setUp()
        Exam.objects.filter(pk=self.math.pk).update(ends_at=timezone.now() - timedelta(hours=1))  # the exam is over
        self.s1 = self.shot(self.ann, self.math)
        self.s2 = self.shot(self.ann, self.math)
        ProctorScreenshot.objects.filter(pk=self.s2.pk).update(kind="webcam")
        self.other = self.shot(self.bob, self.phys)
        self.event(self.ann, self.math, "tab_switch")

    def confirm(self, client, text="math-101"):
        return client.post(self.url, {"confirm": text})

    def test_the_page_shows_what_would_be_deleted(self):
        res = self.as_user("mathteacher").get(self.url)
        self.assertContains(res, "<strong>2</strong> images")
        self.assertContains(res, "Type <code>math-101</code> to confirm")

    def test_typing_the_exam_id_deletes_screenshots_and_photos_but_keeps_the_record(self):
        res = self.confirm(self.as_user("mathteacher"))
        self.assertRedirects(res, "/teacher/exams/math-101/", fetch_redirect_response=False)
        self.assertFalse(ProctorScreenshot.objects.filter(exam=self.math).exists())
        self.assertEqual(len(media_files(self.media)), 1)  # only the other exam's file is left on disk
        self.assertTrue(ProctorScreenshot.objects.filter(pk=self.other.pk).exists())
        self.assertTrue(ProctorEvent.objects.filter(exam=self.math, event_type="tab_switch").exists())
        self.assertTrue(ExamAttempt.objects.filter(pk=self.ann_attempt.pk).exists())
        entry = AuditEntry.objects.get()
        self.assertEqual((entry.action, entry.performed_by), ("evidence deleted", "mathteacher"))
        self.assertIn("2 image(s)", entry.detail)

    def test_a_wrong_confirmation_deletes_nothing(self):
        for text in ("", "math", "MATH-101", "physics-101"):
            res = self.confirm(self.as_user("mathteacher"), text)
            self.assertContains(res, "Type math-101 exactly")
        self.assertEqual(ProctorScreenshot.objects.filter(exam=self.math).count(), 2)
        self.assertEqual(len(media_files(self.media)), 3)

    def test_an_exam_that_is_still_running_is_protected_even_with_the_right_confirmation(self):
        Exam.objects.filter(pk=self.math.pk).update(ends_at=timezone.now() + timedelta(hours=1))
        client = self.as_user("mathteacher")
        self.assertContains(client.get(self.url), "Not allowed yet")
        res = self.confirm(client)
        self.assertContains(res, "only be deleted after the exam has ended")
        self.assertEqual(ProctorScreenshot.objects.filter(exam=self.math).count(), 2)

    def test_an_archived_exam_without_an_end_time_can_be_cleaned(self):
        Exam.objects.filter(pk=self.math.pk).update(ends_at=None, archived=True, archived_at=timezone.now())
        self.confirm(self.as_user("mathteacher"))
        self.assertFalse(ProctorScreenshot.objects.filter(exam=self.math).exists())

    def test_a_missing_file_does_not_break_the_deletion(self):
        os.remove(self.s1.file.path)
        self.confirm(self.as_user("mathteacher"))
        self.assertFalse(ProctorScreenshot.objects.filter(exam=self.math).exists())

    def test_scoping_csrf_and_login(self):
        self.assertEqual(self.as_user("physteacher").get(self.url).status_code, 404)
        self.assertEqual(self.confirm(self.as_user("physteacher")).status_code, 404)
        self.assertEqual(Client().get(self.url).status_code, 302)
        strict = Client(enforce_csrf_checks=True)
        strict.login(username="mathteacher", password="pw")
        self.assertEqual(strict.post(self.url, {"confirm": "math-101"}).status_code, 403)
        self.assertEqual(ProctorScreenshot.objects.filter(exam=self.math).count(), 2)

    def test_the_timeline_simply_has_no_images_afterwards(self):
        self.confirm(self.as_user("mathteacher"))
        html = self.as_user("mathteacher").get("/teacher/exams/math-101/students/1/").content.decode()
        self.assertNotIn("<img", html.split('class="timeline"')[1])
        self.assertIn("Switched away from exam", html)


class RetentionSweepTests(IsolatedMixin, TestCase):
    def setUp(self):
        super().setUp()
        now = timezone.now()
        self.old = make_exam("old", ends_at=now - timedelta(days=100))
        self.recent = make_exam("recent", ends_at=now - timedelta(days=5))
        self.running = make_exam("running", ends_at=now + timedelta(days=1))
        self.archived = make_exam("archived", ends_at=None, archived=True, archived_at=now - timedelta(days=200))
        self.student = make_student()
        for exam in (self.old, self.recent, self.running, self.archived):
            shot = ProctorScreenshot(student=self.student.label, exam=exam)
            shot.file.save("s.png", __import__("django.core.files.base", fromlist=["ContentFile"]).ContentFile(b"x"), save=False)
            shot.save()

    def run_cmd(self, *args):
        out = StringIO()
        call_command("purge_evidence", *args, stdout=out)
        return out.getvalue()

    def remaining(self):
        return sorted(ProctorScreenshot.objects.values_list("exam__exam_id", flat=True))

    def test_dry_run_reports_without_deleting(self):
        text = self.run_cmd("--older-than-days", "90", "--dry-run")
        self.assertIn("Would delete 1 image(s) of old", text)
        self.assertIn("of archived", text)
        self.assertEqual(self.remaining(), ["archived", "old", "recent", "running"])

    def test_only_exams_over_for_longer_than_the_limit_are_purged(self):
        text = self.run_cmd("--older-than-days", "90")
        self.assertIn("Deleted 1 image(s) of old", text)
        self.assertEqual(self.remaining(), ["recent", "running"])
        self.assertEqual(len(media_files(self._media)), 2)

    def test_a_second_run_finds_nothing_and_the_audit_names_the_command(self):
        self.run_cmd("--older-than-days", "90")
        self.assertIn("Nothing to delete", self.run_cmd("--older-than-days", "90"))
        self.assertEqual(set(AuditEntry.objects.values_list("performed_by", flat=True)), {"purge_evidence"})
        self.assertEqual(AuditEntry.objects.count(), 2)

    def test_a_short_limit_still_never_touches_a_running_exam(self):
        self.run_cmd("--older-than-days", "0")
        self.assertIn("running", self.remaining())


class DeactivationTests(IsolatedMixin, TestCase):
    def setUp(self):
        super().setUp()
        get_user_model().objects.create_superuser("root", "r@example.com", "pw")
        self.admin = Client()
        self.admin.login(username="root", password="pw")
        self.a = make_student(roll="1", name="Ann", batch=81)
        self.b = make_student(roll="2", name="Bob", email="b@x.com", batch=81)
        self.c = make_student(roll="3", name="Cy", email="c@x.com", batch=82)

    def login(self, roll):
        return APIClient().post("/api/login/", {"roll_number": roll, "password": PASSWORD}, format="json").status_code

    def test_the_admin_action_stops_logins_and_ends_sessions(self):
        client, _ = authed_client(self.a)
        self.admin.post("/admin/proctoring/student/", {"action": "deactivate_selected", "_selected_action": [self.a.pk]}, follow=True)
        self.a.refresh_from_db()
        self.assertFalse(self.a.is_active)
        self.assertEqual(self.login("1"), 401)
        self.assertEqual(client.get("/api/exams/").status_code, 401)
        self.assertFalse(StudentToken.objects.filter(student=self.a).exists())
        self.assertEqual(self.login("2"), 200)  # others untouched

    def test_reactivate(self):
        Student.objects.filter(pk=self.a.pk).update(is_active=False)
        self.admin.post("/admin/proctoring/student/", {"action": "reactivate_selected", "_selected_action": [self.a.pk]}, follow=True)
        self.assertEqual(self.login("1"), 200)

    def test_the_whole_batch_command(self):
        out = StringIO()
        call_command("deactivate_batch", "81", "--dry-run", stdout=out)
        self.assertIn("Would deactivate 2 student(s) of batch 81", out.getvalue())
        self.assertEqual(Student.objects.filter(is_active=True).count(), 3)
        call_command("deactivate_batch", "81", stdout=out)
        self.assertEqual(sorted(Student.objects.filter(is_active=False).values_list("roll_number", flat=True)), ["1", "2"])
        self.assertEqual(self.login("3"), 200)

    def test_an_active_student_cannot_be_deleted_but_an_inactive_one_can(self):
        self.assertEqual(self.admin.get(f"/admin/proctoring/student/{self.a.pk}/delete/").status_code, 403)
        res = self.admin.post("/admin/proctoring/student/", {"action": "delete_selected", "_selected_action": [self.a.pk], "post": "yes"}, follow=True)
        self.assertTrue(Student.objects.filter(pk=self.a.pk).exists())
        Student.objects.filter(pk=self.a.pk).update(is_active=False)
        self.assertEqual(self.admin.get(f"/admin/proctoring/student/{self.a.pk}/delete/").status_code, 200)
        self.admin.post(f"/admin/proctoring/student/{self.a.pk}/delete/", {"post": "yes"})
        self.assertFalse(Student.objects.filter(pk=self.a.pk).exists())


class AuditAdminTests(TestCase):
    def test_audit_entries_are_visible_but_read_only(self):
        get_user_model().objects.create_superuser("root", "r@example.com", "pw")
        exam = make_exam("math-101")
        services.archive_exam(exam, "root")
        client = Client()
        client.login(username="root", password="pw")
        self.assertContains(client.get("/admin/proctoring/auditentry/"), "archived")
        self.assertEqual(client.get("/admin/proctoring/auditentry/add/").status_code, 403)
        entry = AuditEntry.objects.get()
        self.assertEqual(client.post(f"/admin/proctoring/auditentry/{entry.pk}/delete/", {"post": "yes"}).status_code, 403)

    def test_the_audit_survives_deleting_the_exam(self):
        exam = make_exam("gone")
        services.archive_exam(exam, "root")
        exam.delete()
        entry = AuditEntry.objects.get()
        self.assertIsNone(entry.exam)
        self.assertEqual(entry.exam_label, "gone (gone)")
