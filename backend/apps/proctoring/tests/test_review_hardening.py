"""Regression tests for the issues found in the full review (security, data integrity, edge cases)."""
import uuid
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase, APITransactionTestCase

from apps.proctoring import services
from apps.proctoring.event_types import CLIENT_SENDABLE, SERVER_ONLY, EventType
from apps.proctoring.models import AuditEntry, Exam, ExamAttempt, ProctorEvent, ProctorScreenshot, Student

from .helpers import PASSWORD, IsolatedMixin, authed_client, make_exam, make_student
from .test_dashboard import DashboardBase

PNG = b"\x89PNG\r\n\x1a\nfake"
JPG = b"\xff\xd8\xff\xe0fake"


class EventIntegrityTests(IsolatedMixin, APITransactionTestCase):
    def setUp(self):
        super().setUp()
        make_exam("math-101")
        make_exam("other-batch", batch=99)
        self.client, _ = authed_client(make_student())

    def event(self, event_type="tab_switch", exam="math-101", **extra):
        return self.client.post("/api/events/", {"exam_id": exam, "event_type": event_type, "client_id": str(uuid.uuid4()), **extra}, format="json")

    def test_events_the_server_writes_cannot_be_forged_by_a_student(self):
        for forged in SERVER_ONLY:
            self.assertEqual(self.event(forged).status_code, 400, forged)
        self.assertFalse(ProctorEvent.objects.exists())

    def test_unknown_event_types_are_refused(self):
        self.assertEqual(self.event("made_up").status_code, 400)

    def test_every_event_the_app_sends_is_accepted(self):
        for event_type in CLIENT_SENDABLE:
            self.assertEqual(self.event(event_type).status_code, 201, event_type)
        self.assertEqual(ProctorEvent.objects.count(), len(CLIENT_SENDABLE))

    def test_the_two_lists_do_not_overlap_and_cover_everything(self):
        self.assertEqual(set(CLIENT_SENDABLE) | {e.value for e in SERVER_ONLY}, {e.value for e in EventType})
        self.assertFalse(set(CLIENT_SENDABLE) & {e.value for e in SERVER_ONLY})

    def test_events_cannot_be_planted_in_another_batchs_exam(self):
        res = self.event(exam="other-batch")
        self.assertEqual(res.status_code, 400)
        self.assertIn("exam_id", res.data)
        self.assertFalse(ProctorEvent.objects.exists())

    def test_consent_cannot_be_posted_for_another_batchs_exam(self):
        self.assertEqual(self.client.post("/api/consent/", {"exam_id": "other-batch"}, format="json").status_code, 400)

    def test_late_events_for_an_archived_exam_are_still_accepted(self):
        Exam.objects.filter(exam_id="math-101").update(archived=True)
        self.assertEqual(self.event().status_code, 201)  # a student who finished offline may flush after archiving

    def test_a_future_timestamp_from_a_wrong_clock_is_clamped_not_dropped(self):
        future = (timezone.now() + timedelta(days=3)).isoformat()
        res = self.event(timestamp=future)
        self.assertEqual(res.status_code, 201)
        self.assertLessEqual(ProctorEvent.objects.get().timestamp, timezone.now())

    def test_old_timestamps_from_an_offline_queue_are_kept(self):
        old = timezone.now() - timedelta(hours=5)
        self.event(timestamp=old.isoformat())
        self.assertAlmostEqual(ProctorEvent.objects.get().timestamp.timestamp(), old.timestamp(), delta=1)


class UploadSafetyTests(IsolatedMixin, APITransactionTestCase):
    def setUp(self):
        super().setUp()
        make_exam("math-101")
        make_exam("other-batch", batch=99)
        self.client, _ = authed_client(make_student())

    def upload(self, name="s.png", data=PNG, content_type="image/png", exam="math-101"):
        return self.client.post(
            "/api/screenshots/",
            {"exam_id": exam, "file": SimpleUploadedFile(name, data, content_type=content_type), "client_id": str(uuid.uuid4())},
            format="multipart",
        )

    def test_real_png_and_jpeg_are_accepted_in_any_letter_case(self):
        for name, data in (("a.png", PNG), ("b.jpg", JPG), ("c.JPEG", JPG), ("d.PNG", PNG)):
            self.assertEqual(self.upload(name, data, "image/jpeg" if data is JPG else "image/png").status_code, 201, name)

    def test_a_script_cannot_be_stored_by_claiming_to_be_an_image(self):
        for name in ("evil.html", "evil.svg", "evil.js", "evil", "evil.png.html"):
            res = self.upload(name, b"<script>alert(1)</script>", "image/png")
            self.assertEqual(res.status_code, 400, name)
        self.assertFalse(ProctorScreenshot.objects.exists())

    def test_the_bytes_must_match_the_extension(self):
        self.assertEqual(self.upload("fake.png", b"not an image at all").status_code, 400)
        self.assertEqual(self.upload("swap.png", JPG).status_code, 400)  # JPEG bytes named .png
        self.assertEqual(self.upload("swap.jpg", PNG).status_code, 400)

    def test_screenshots_cannot_be_uploaded_to_another_batchs_exam(self):
        self.assertEqual(self.upload(exam="other-batch").status_code, 400)


class StoredFileServingTests(DashboardBase):
    def test_images_are_served_with_a_fixed_safe_type_and_locked_down_headers(self):
        shot = self.shot(self.ann, self.math)
        res = self.as_user("mathteacher").get(f"/teacher/exams/math-101/screenshots/{shot.pk}/")
        self.assertEqual(res["Content-Type"], "image/png")
        self.assertEqual(res["X-Content-Type-Options"], "nosniff")
        self.assertIn("default-src 'none'", res["Content-Security-Policy"])

    def test_a_legacy_non_image_file_is_never_rendered_in_the_teachers_browser(self):
        from django.core.files.base import ContentFile

        shot = ProctorScreenshot(student=self.ann.label, exam=self.math)
        shot.file.save("old.html", ContentFile(b"<script>alert(1)</script>"), save=False)
        shot.save()
        res = self.as_user("mathteacher").get(f"/teacher/exams/math-101/screenshots/{shot.pk}/")
        self.assertEqual(res["Content-Type"], "application/octet-stream")
        self.assertEqual(res["Content-Disposition"], "attachment")


class ConfigApiValidationTests(IsolatedMixin, APITestCase):
    def setUp(self):
        super().setUp()
        make_exam("math-101")

    def post(self, body):
        return APIClient().post("/api/config/math-101/", body, format="json", HTTP_X_ADMIN_KEY="k")

    @override_settings(ADMIN_API_KEY="k")
    def test_the_api_enforces_the_same_rules_as_the_admin(self):
        cases = [
            ({"written_enabled": False}, "written_enabled"),  # no part left
            ({"form_url": ""}, "form_url"),
            ({"practical_enabled": True}, "practical_instructions"),
        ]
        for body, field in cases:
            res = self.post(body)
            self.assertEqual(res.status_code, 400, body)
            self.assertIn(field, res.data)
        exam = Exam.objects.get(exam_id="math-101")
        self.assertEqual((exam.written_enabled, exam.practical_enabled, bool(exam.form_url)), (True, False, True))

    @override_settings(ADMIN_API_KEY="k")
    def test_valid_changes_still_work_and_the_batch_is_untouched(self):
        res = self.post({"practical_enabled": True, "practical_instructions": "Do the lab", "grace_seconds": 6, "batch": 5})
        self.assertEqual(res.status_code, 200)
        exam = Exam.objects.get(exam_id="math-101")
        self.assertEqual((exam.practical_enabled, exam.grace_seconds, exam.batch), (True, 6, 81))


class LockoutFairnessTests(IsolatedMixin, APITestCase):
    def setUp(self):
        super().setUp()
        make_student()

    def login(self, ip, password="wrong"):
        return APIClient().post("/api/login/", {"roll_number": "1", "password": password}, format="json", REMOTE_ADDR=ip)

    def test_a_classmate_failing_logins_cannot_lock_the_real_student_out(self):
        for _ in range(5):
            self.login("10.0.0.9")
        self.assertEqual(self.login("10.0.0.9", PASSWORD).status_code, 429)  # the attacker's own address is locked
        self.assertEqual(self.login("10.0.0.20", PASSWORD).status_code, 200)  # the student from their own computer is fine

    def test_guessing_from_many_addresses_still_hits_the_ceiling(self):
        for i in range(50):
            self.login(f"10.1.{i // 250}.{i % 250 + 1}")
        self.assertEqual(self.login("10.9.9.9", PASSWORD).status_code, 429)

    def test_success_resets_only_that_addresses_counter(self):
        for _ in range(4):
            self.login("10.0.0.9")
        self.assertEqual(self.login("10.0.0.9", PASSWORD).status_code, 200)
        for _ in range(4):
            self.login("10.0.0.9")
        self.assertEqual(self.login("10.0.0.9", PASSWORD).status_code, 200)

    def test_activation_guessing_is_limited_per_address_too(self):
        Student.objects.filter(roll_number="1").update(password="")
        post = lambda ip, email: APIClient().post("/api/auth/activate/", {"roll_number": "1", "email": email}, format="json", REMOTE_ADDR=ip)
        for _ in range(5):
            post("10.0.0.9", "x@example.com")
        self.assertEqual(post("10.0.0.9", "ann@example.com").status_code, 429)
        self.assertEqual(post("10.0.0.20", "ann@example.com").status_code, 200)

    def test_change_password_lockout_is_per_address_as_well(self):
        client, _ = authed_client(Student.objects.get(roll_number="1"))
        change = lambda ip, cur: client.post("/api/auth/change-password/", {"current_password": cur, "new_password": "a-new-pass-123"}, format="json", REMOTE_ADDR=ip)
        for _ in range(5):
            change("10.0.0.9", "nope")
        self.assertEqual(change("10.0.0.9", PASSWORD).status_code, 429)
        self.assertEqual(change("10.0.0.20", PASSWORD).status_code, 200)


class ArchiveLeftoverTests(DashboardBase):
    def test_leftover_attempts_are_completed_when_the_exams_time_is_over(self):
        Exam.objects.filter(pk=self.math.pk).update(ends_at=timezone.now() - timedelta(hours=1))
        self.exam = Exam.objects.get(pk=self.math.pk)
        services.archive_exam(self.exam, "mathteacher")
        self.ann_attempt.refresh_from_db()
        self.assertEqual(self.ann_attempt.status, "completed")
        self.assertIsNotNone(self.ann_attempt.ended_at)
        self.assertEqual(sorted(AuditEntry.objects.values_list("action", flat=True)), ["archived", "attempts completed"])

    def test_students_in_progress_still_block_archiving_while_the_exam_is_open(self):
        with self.assertRaises(services.RuleError):
            services.archive_exam(self.math, "mathteacher")
        self.ann_attempt.refresh_from_db()
        self.assertEqual(self.ann_attempt.status, "in_progress")


class RollNumbersWithSlashesTests(DashboardBase):
    def test_timeline_works_for_rolls_like_2021_001(self):
        weird = make_student(roll="2021/001", name="Slash Kid", email="s@x.com")
        ExamAttempt.objects.create(student=weird, exam=self.math)
        self.event(weird, self.math, "tab_switch")
        client = self.as_user("mathteacher")
        self.assertEqual(client.get("/teacher/exams/math-101/students/2021/001/").status_code, 200)
        self.assertEqual(client.get("/teacher/exams/math-101/students/2021%2F001/").status_code, 200)
        self.assertContains(client.get("/teacher/exams/math-101/students/2021/001/"), "Slash Kid")

    def test_rolls_with_spaces_and_dashes_work_too(self):
        odd = make_student(roll="CSE-21 07", name="Odd Roll", email="o@x.com")
        ExamAttempt.objects.create(student=odd, exam=self.math)
        self.assertEqual(self.as_user("mathteacher").get("/teacher/exams/math-101/students/CSE-21%2007/").status_code, 200)

    def test_login_api_accepts_such_rolls(self):
        make_student(roll="2021/001", name="Slash Kid", email="s@x.com")
        res = APIClient().post("/api/login/", {"roll_number": "2021/001", "password": PASSWORD}, format="json")
        self.assertEqual(res.status_code, 200)


class ProductionSafetyChecksTests(SimpleTestCase):
    def test_default_secret_key_is_flagged_outside_debug(self):
        from apps.proctoring.checks import secret_key_check

        with override_settings(DEBUG=False, SECRET_KEY="dev-only-insecure-key-change-me"):
            self.assertEqual([w.id for w in secret_key_check(None)], ["proctoring.W002"])
        with override_settings(DEBUG=False, SECRET_KEY="a-long-random-production-key-0123456789"):
            self.assertEqual(secret_key_check(None), [])
        with override_settings(DEBUG=True, SECRET_KEY="dev-only-insecure-key-change-me"):
            self.assertEqual(secret_key_check(None), [])


class MonitorPageSessionHandlingTests(DashboardBase):
    def test_the_monitor_script_tells_the_teacher_when_the_session_has_expired(self):
        html = self.as_user("mathteacher").get("/teacher/exams/math-101/").content.decode()
        self.assertIn('id="notice"', html)
        self.assertIn("Your session has expired", html)
        self.assertIn("res.redirected", html)

    def test_an_expired_session_gets_a_redirect_not_json(self):
        res = Client().get("/teacher/exams/math-101/live.json")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/teacher/login/", res["Location"])


class CsvForExcelTests(DashboardBase):
    def test_all_three_downloads_carry_a_bom_and_keep_non_english_names_intact(self):
        bangla = make_student(roll="9", name="রহিম উদ্দিন", email="r@x.com")
        ExamAttempt.objects.create(student=bangla, exam=self.math)
        self.event(bangla, self.math, "tab_switch")
        client = self.as_user("mathteacher")
        for url in ("/teacher/exams/math-101/summary.csv", "/teacher/exams/math-101/events.csv"):
            body = client.get(url).content
            self.assertTrue(body.startswith(b"\xef\xbb\xbf"), url)
            self.assertIn("রহিম উদ্দিন", body.decode("utf-8-sig"), url)
        marks = client.post("/teacher/exams/math-101/marks/", {"responses": SimpleUploadedFile("r.csv", b"Roll number,Score\n9,5 / 10\n"), "download": "1"})
        self.assertTrue(marks.content.startswith(b"\xef\xbb\xbf"))
        self.assertIn("রহিম উদ্দিন", marks.content.decode("utf-8-sig"))


class TeacherStudentsPageTests(DashboardBase):
    def setUp(self):
        super().setUp()
        self.cara = make_student(roll="3", name="Cara", email="c@x.com", batch=81)  # activated
        self.dan = make_student(roll="4", name="Dan", email="d@x.com", batch=81, activated=False)
        self.eve = make_student(roll="5", name="Eve", email="e@x.com", batch=82)  # another batch
        self.url = "/teacher/exams/math-101/students/"

    def new_password_url(self, student, exam="math-101"):
        return f"/teacher/exams/{exam}/students/{student.pk}/new-password/"

    def test_the_page_lists_only_the_exams_batch_with_account_state(self):
        html = self.as_user("mathteacher").get(self.url).content.decode()
        for name in ("Ann", "Bob", "Cara", "Dan"):
            self.assertIn(name, html)
        self.assertNotIn("Eve", html)
        self.assertIn("no password yet", html)
        self.assertIn("has password", html)

    def test_an_exam_without_a_batch_shows_a_notice_instead_of_students(self):
        Exam.objects.filter(pk=self.math.pk).update(batch=None)
        res = self.as_user("mathteacher").get(self.url)
        self.assertContains(res, "has no batch yet")
        self.assertNotContains(res, "Cara")

    def test_a_forgotten_password_gets_a_new_one_and_the_old_one_stops_working(self):
        client_api, _ = authed_client(self.cara)
        res = self.as_user("mathteacher").post(self.new_password_url(self.cara))
        self.assertEqual(res.status_code, 200)
        self.assertIn("no-store", res["Cache-Control"])
        new = res.content.decode().split("<code>")[1].split("</code>")[0]
        self.assertEqual(APIClient().post("/api/login/", {"roll_number": "3", "password": PASSWORD}, format="json").status_code, 401)
        self.assertEqual(APIClient().post("/api/login/", {"roll_number": "3", "password": new}, format="json").status_code, 200)
        self.assertEqual(client_api.get("/api/exams/").status_code, 401)  # the old session ended

    def test_only_one_student_changes_and_only_from_this_exams_batch(self):
        before = Student.objects.get(pk=self.ann.pk).password
        self.as_user("mathteacher").post(self.new_password_url(self.cara))
        self.assertEqual(Student.objects.get(pk=self.ann.pk).password, before)
        for other in (self.eve,):  # batch 82 is not this exam's batch
            self.assertEqual(self.as_user("mathteacher").post(self.new_password_url(other)).status_code, 404)

    def test_deactivated_students_cannot_be_given_passwords(self):
        Student.objects.filter(pk=self.cara.pk).update(is_active=False)
        self.assertEqual(self.as_user("mathteacher").post(self.new_password_url(self.cara)).status_code, 404)

    def test_other_subjects_teacher_methods_csrf_and_login(self):
        self.assertEqual(self.as_user("physteacher").get(self.url).status_code, 404)
        self.assertEqual(self.as_user("physteacher").post(self.new_password_url(self.cara)).status_code, 404)
        self.assertEqual(self.as_user("mathteacher").get(self.new_password_url(self.cara)).status_code, 405)
        self.assertEqual(Client().post(self.new_password_url(self.cara)).status_code, 302)
        strict = Client(enforce_csrf_checks=True)
        strict.login(username="mathteacher", password="pw")
        self.assertEqual(strict.post(self.new_password_url(self.cara)).status_code, 403)
        self.assertTrue(Student.objects.get(pk=self.cara.pk).check_password(PASSWORD))

    def test_the_monitor_links_to_the_page_and_names_are_escaped(self):
        Student.objects.filter(pk=self.cara.pk).update(name="<script>alert(1)</script>")
        html = self.as_user("mathteacher").get(self.url).content.decode()
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertContains(self.as_user("mathteacher").get("/teacher/exams/math-101/"), 'href="/teacher/exams/math-101/students/"')


class BatchCorrectionTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        get_user_model().objects.create_superuser("root", "r@example.com", "pw")
        self.client = Client()
        self.client.login(username="root", password="pw")
        self.student = make_student(roll="1", batch=95)

    def post(self, batch, correct=False):
        data = {"roll_number": "1", "name": "Ann", "email": "ann@example.com", "batch": batch, "is_active": "on",
                "batch_changes-TOTAL_FORMS": 0, "batch_changes-INITIAL_FORMS": 0}
        if correct:
            data["correct_batch"] = "on"
        return self.client.post(f"/admin/proctoring/student/{self.student.pk}/change/", data)

    def test_lowering_the_batch_is_still_refused_without_the_correction_box(self):
        res = self.post(94)
        self.assertContains(res, "Batch can only move forward")
        self.student.refresh_from_db()
        self.assertEqual(self.student.batch, 95)

    def test_an_admin_can_correct_a_typo_and_it_is_recorded_as_a_correction(self):
        self.assertEqual(self.post(81, correct=True).status_code, 302)
        self.student.refresh_from_db()
        self.assertEqual(self.student.batch, 81)
        change = self.student.batch_changes.get()
        self.assertEqual((change.from_batch, change.to_batch, change.changed_by), (95, 81, "root (correction)"))

    def test_forward_moves_are_not_labelled_corrections(self):
        self.post(96, correct=True)
        self.assertEqual(self.student.batch_changes.get().changed_by, "root")

    def test_the_model_itself_still_refuses_a_backward_move_in_code(self):
        from django.core.exceptions import ValidationError

        student = Student.objects.get(pk=self.student.pk)
        student.batch = 80
        with self.assertRaises(ValidationError):
            student.save()
