import json
import shutil
import tempfile
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.proctoring import scoring, services
from apps.proctoring.models import ExamAttempt, ProctorEvent, ProctorScreenshot, StudentToken

from .helpers import authed_client, make_exam, make_student


class ScoringTests(TestCase):
    def test_weights_and_flags(self):
        self.assertEqual(scoring.score({"tab_switch": 3, "display_added": 1, "returned_to_exam": 9}), 6)
        self.assertEqual(scoring.flag_for(0), "clean")
        self.assertEqual(scoring.flag_for(1), "review")
        self.assertEqual(scoring.flag_for(4), "review")
        self.assertEqual(scoring.flag_for(5), "flagged")

    def test_every_weighted_type_has_a_label(self):
        self.assertFalse(set(scoring.WEIGHTS) - set(scoring.EVENT_LABELS))


class DashboardBase(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)
        self.addCleanup(shutil.rmtree, self.media, True)

        self.math = make_exam("math-101", name="Mathematics")
        self.phys = make_exam("physics-101", name="Physics")
        for user, exam in (("mathteacher", "math-101"), ("physteacher", "physics-101")):
            call_command("create_teacher", user, "--exams", exam, "--password", "pw", stdout=StringIO())
        self.root = get_user_model().objects.create_superuser("root", "r@example.com", "pw")

        self.ann = make_student(roll="1", name="Ann", batch=81)
        self.bob = make_student(roll="2", name="Bob", email="b@example.com", batch=81)
        self.ann_attempt = ExamAttempt.objects.create(student=self.ann, exam=self.math)
        self.bob_attempt = ExamAttempt.objects.create(student=self.bob, exam=self.phys)

    def as_user(self, username):
        client = Client()
        self.assertTrue(client.login(username=username, password="pw"))
        return client

    def event(self, student, exam, event_type, detail="", ago=0):
        return ProctorEvent.objects.create(
            student=student.label, exam=exam, event_type=event_type, detail=detail, timestamp=timezone.now() - timedelta(seconds=ago)
        )

    def shot(self, student, exam, ago=0):
        shot = ProctorScreenshot(student=student.label, exam=exam, timestamp=timezone.now() - timedelta(seconds=ago))
        shot.file.save("s.png", ContentFile(b"\x89PNG-bytes"), save=False)
        shot.save()
        return shot

    def live(self, client, exam_id="math-101"):
        res = client.get(f"/teacher/exams/{exam_id}/live.json")
        self.assertEqual(res.status_code, 200)
        return res.json()["rows"]


class AccessControlTests(DashboardBase):
    def test_anonymous_is_sent_to_login(self):
        for url in ("/teacher/", "/teacher/exams/math-101/", "/teacher/exams/math-101/live.json",
                    "/teacher/exams/math-101/summary.csv", "/teacher/exams/math-101/events.csv"):
            res = Client().get(url)
            self.assertEqual(res.status_code, 302, url)
            self.assertIn("/teacher/login/", res["Location"])

    def test_non_staff_user_is_refused(self):
        get_user_model().objects.create_user("plain", password="pw")
        client = Client()
        client.login(username="plain", password="pw")
        self.assertEqual(client.get("/teacher/").status_code, 403)

    def test_exam_list_is_scoped(self):
        res = self.as_user("mathteacher").get("/teacher/")
        self.assertContains(res, "math-101")
        self.assertNotContains(res, "physics-101")

    def test_other_subjects_pages_404(self):
        client = self.as_user("mathteacher")
        for url in ("/teacher/exams/physics-101/", "/teacher/exams/physics-101/live.json",
                    "/teacher/exams/physics-101/summary.csv", "/teacher/exams/physics-101/events.csv",
                    "/teacher/exams/physics-101/students/2/"):
            self.assertEqual(client.get(url).status_code, 404, url)

    def test_superuser_sees_everything(self):
        client = self.as_user("root")
        self.assertContains(client.get("/teacher/"), "physics-101")
        self.assertEqual(client.get("/teacher/exams/physics-101/").status_code, 200)

    def test_student_from_another_exam_has_no_timeline_here(self):
        self.assertEqual(self.as_user("mathteacher").get("/teacher/exams/math-101/students/2/").status_code, 404)


class LiveMonitorTests(DashboardBase):
    def test_rows_show_counts_score_flag_and_are_scoped_to_the_exam(self):
        for _ in range(3):
            self.event(self.ann, self.math, "tab_switch")
        self.event(self.ann, self.math, "display_added", "2 displays")
        self.event(self.bob, self.phys, "tab_switch")
        rows = self.live(self.as_user("mathteacher"))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row["roll_number"], row["tab_switches"], row["score"], row["flag"]), ("1", 3, 6, "flagged"))
        self.assertEqual(row["counts"], {"tab_switch": 3, "display_added": 1})
        self.assertIsNotNone(row["last_event_at"])

    def test_online_offline_and_ended_states(self):
        token = StudentToken.objects.create(
            student=self.ann, key_hash="x", expires_at=timezone.now() + timedelta(hours=1), last_seen_at=timezone.now()
        )
        client = self.as_user("mathteacher")
        self.assertEqual(self.live(client)[0]["state"], "online")
        token.last_seen_at = timezone.now() - timedelta(minutes=5)
        token.save()
        self.assertEqual(self.live(client)[0]["state"], "offline")
        token.delete()
        self.assertEqual(self.live(client)[0]["state"], "offline")  # in progress, no session
        ExamAttempt.objects.filter(pk=self.ann_attempt.pk).update(status="quit")
        self.assertEqual(self.live(client)[0]["state"], "ended")

    def test_worst_students_come_first(self):
        carl = make_student(roll="3", name="Carl", email="c@example.com")
        ExamAttempt.objects.create(student=carl, exam=self.math)
        self.event(carl, self.math, "devtools_attempt")
        self.event(self.ann, self.math, "tab_switch")
        self.assertEqual([r["roll_number"] for r in self.live(self.as_user("mathteacher"))], ["3", "1"])

    def test_query_count_does_not_grow_with_students(self):
        client = self.as_user("mathteacher")
        client.get("/teacher/exams/math-101/live.json")  # warm session

        def count():
            with CaptureQueriesContext(connection) as ctx:
                client.get("/teacher/exams/math-101/live.json")
            return len(ctx)

        small = count()
        for i in range(10, 30):
            student = make_student(roll=str(i), name=f"S{i}", email=f"s{i}@example.com")
            ExamAttempt.objects.create(student=student, exam=self.math)
            StudentToken.objects.create(student=student, key_hash=f"h{i}", expires_at=timezone.now() + timedelta(hours=1), last_seen_at=timezone.now())
            for _ in range(5):
                self.event(student, self.math, "tab_switch")
        self.assertEqual(count(), small)
        self.assertEqual(len(self.live(client)), 21)

    def test_monitor_page_embeds_data_safely(self):
        evil = make_student(roll="9", name="</script><script>alert(1)</script>", email="e@example.com")
        ExamAttempt.objects.create(student=evil, exam=self.math)
        res = self.as_user("mathteacher").get("/teacher/exams/math-101/")
        self.assertNotContains(res, "</script><script>alert(1)")
        self.assertContains(res, "\\u003c/script\\u003e")


class TimelineTests(DashboardBase):
    def test_timeline_merges_events_and_screenshots_in_order(self):
        self.event(self.ann, self.math, "tab_switch", ago=30)
        shot = self.shot(self.ann, self.math, ago=29)
        self.event(self.ann, self.math, "returned_to_exam", ago=10)
        res = self.as_user("mathteacher").get("/teacher/exams/math-101/students/1/")
        html = res.content.decode()
        self.assertLess(html.index("Switched away from exam"), html.index(f"/screenshots/{shot.pk}/"))
        self.assertLess(html.index(f"/screenshots/{shot.pk}/"), html.index("Returned to exam"))

    def test_other_students_data_is_not_shown(self):
        self.event(self.ann, self.math, "tab_switch")
        self.event(self.bob, self.math, "devtools_attempt")
        html = self.as_user("mathteacher").get("/teacher/exams/math-101/students/1/").content.decode()
        self.assertIn("Switched away from exam", html)
        self.assertNotIn("developer tools", html)

    def test_event_detail_is_escaped(self):
        self.event(self.ann, self.math, "blocked_app_detected", "<img src=x onerror=alert(1)>")
        html = self.as_user("mathteacher").get("/teacher/exams/math-101/students/1/").content.decode()
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;img src=x", html)

    def test_timeline_query_count_is_constant(self):
        client = self.as_user("mathteacher")
        client.get("/teacher/")
        for _ in range(3):
            self.event(self.ann, self.math, "tab_switch")
        with CaptureQueriesContext(connection) as small:
            client.get("/teacher/exams/math-101/students/1/")
        for _ in range(30):
            self.event(self.ann, self.math, "tab_switch")
            self.shot(self.ann, self.math)
        with CaptureQueriesContext(connection) as big:
            client.get("/teacher/exams/math-101/students/1/")
        self.assertEqual(len(small), len(big))


class ScreenshotAccessTests(DashboardBase):
    def test_owner_teacher_can_download(self):
        shot = self.shot(self.ann, self.math)
        res = self.as_user("mathteacher").get(f"/teacher/exams/math-101/screenshots/{shot.pk}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(b"".join(res.streaming_content), b"\x89PNG-bytes")
        self.assertEqual(res["Content-Type"], "image/png")

    def test_other_teacher_and_anonymous_cannot(self):
        shot = self.shot(self.ann, self.math)
        url = f"/teacher/exams/math-101/screenshots/{shot.pk}/"
        self.assertEqual(self.as_user("physteacher").get(url).status_code, 404)
        self.assertEqual(Client().get(url).status_code, 302)
        # the exam in the URL cannot be swapped to dodge the scope check
        self.assertEqual(self.as_user("physteacher").get(f"/teacher/exams/physics-101/screenshots/{shot.pk}/").status_code, 404)

    def test_screenshots_are_not_publicly_served_from_media(self):
        shot = self.shot(self.ann, self.math)
        self.assertEqual(Client().get(shot.file.url).status_code, 404)

    def test_missing_file_is_a_404_not_a_500(self):
        shot = self.shot(self.ann, self.math)
        shot.file.delete(save=False)
        self.assertEqual(self.as_user("mathteacher").get(f"/teacher/exams/math-101/screenshots/{shot.pk}/").status_code, 404)


class CsvTests(DashboardBase):
    def test_summary_csv(self):
        self.event(self.ann, self.math, "tab_switch")
        self.event(self.ann, self.math, "tab_switch")
        res = self.as_user("mathteacher").get("/teacher/exams/math-101/summary.csv")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn('filename="math-101-summary.csv"', res["Content-Disposition"])
        lines = res.content.decode().strip().splitlines()
        header = lines[0].split(",")
        self.assertEqual(header[:8], ["roll_number", "name", "batch", "attempt_status", "started_at", "last_seen", "score", "flag"])
        self.assertEqual(len(lines), 2)  # header + Ann only (Bob is in physics)
        row = dict(zip(header, lines[1].split(",")))
        self.assertEqual((row["roll_number"], row["score"], row["flag"], row["tab_switch"]), ("1", "2", "review", "2"))

    def test_events_csv_is_scoped_and_ordered(self):
        self.event(self.ann, self.math, "returned_to_exam", ago=1)
        self.event(self.ann, self.math, "tab_switch", ago=5)
        self.event(self.bob, self.phys, "tab_switch")
        text = self.as_user("mathteacher").get("/teacher/exams/math-101/events.csv").content.decode()
        self.assertNotIn("Bob", text)
        self.assertLess(text.index("tab_switch"), text.index("returned_to_exam"))

    def test_formula_injection_is_neutralised(self):
        evil = make_student(roll="7", name='=HYPERLINK("http://evil","x")', email="ev@example.com")
        ExamAttempt.objects.create(student=evil, exam=self.math)
        self.event(evil, self.math, "blocked_app_detected", "+cmd|' /C calc'!A0")
        client = self.as_user("mathteacher")
        summary = client.get("/teacher/exams/math-101/summary.csv").content.decode()
        events = client.get("/teacher/exams/math-101/events.csv").content.decode()
        self.assertNotIn(",=HYPERLINK", summary)
        self.assertIn("'=HYPERLINK", summary)
        self.assertNotIn(",+cmd", events)
        self.assertIn("'+cmd", events)


class AttemptActionTests(DashboardBase):
    def test_force_end_via_dashboard(self):
        client_api, _ = authed_client(self.ann)
        res = self.as_user("mathteacher").post(f"/teacher/exams/math-101/attempts/{self.ann_attempt.pk}/force-end/")
        self.assertEqual(res.json(), {"ok": True, "changed": 1})
        self.ann_attempt.refresh_from_db()
        self.assertEqual(self.ann_attempt.status, "force_ended")
        self.assertEqual(client_api.get("/api/exams/").status_code, 401)
        self.assertEqual(ProctorEvent.objects.get(event_type="force_ended").detail, "mathteacher")

    def test_reset_via_dashboard(self):
        self.as_user("mathteacher").post(f"/teacher/exams/math-101/attempts/{self.ann_attempt.pk}/reset/")
        self.assertFalse(ExamAttempt.objects.filter(pk=self.ann_attempt.pk).exists())

    def test_cannot_act_on_another_subjects_attempt(self):
        client = self.as_user("mathteacher")
        self.assertEqual(client.post(f"/teacher/exams/math-101/attempts/{self.bob_attempt.pk}/force-end/").status_code, 404)
        self.assertEqual(client.post(f"/teacher/exams/physics-101/attempts/{self.bob_attempt.pk}/force-end/").status_code, 404)
        self.bob_attempt.refresh_from_db()
        self.assertEqual(self.bob_attempt.status, "in_progress")

    def test_get_is_not_allowed_and_csrf_is_enforced(self):
        url = f"/teacher/exams/math-101/attempts/{self.ann_attempt.pk}/force-end/"
        self.assertEqual(self.as_user("mathteacher").get(url).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.login(username="mathteacher", password="pw")
        self.assertEqual(strict.post(url).status_code, 403)
        self.ann_attempt.refresh_from_db()
        self.assertEqual(self.ann_attempt.status, "in_progress")

    def test_anonymous_cannot_act(self):
        res = Client().post(f"/teacher/exams/math-101/attempts/{self.ann_attempt.pk}/force-end/")
        self.assertEqual(res.status_code, 302)
        self.ann_attempt.refresh_from_db()
        self.assertEqual(self.ann_attempt.status, "in_progress")

    def test_service_ignores_already_ended_attempts(self):
        ExamAttempt.objects.filter(pk=self.ann_attempt.pk).update(status="quit")
        self.assertEqual(services.force_end_attempts(ExamAttempt.objects.filter(pk=self.ann_attempt.pk), "t"), 0)
        self.assertFalse(ProctorEvent.objects.filter(event_type="force_ended").exists())


class WebcamDashboardTests(DashboardBase):
    def test_timeline_labels_webcam_photos_and_screenshots_differently(self):
        cam = self.shot(self.ann, self.math)
        ProctorScreenshot.objects.filter(pk=cam.pk).update(kind="webcam")
        self.shot(self.ann, self.math)
        html = self.as_user("mathteacher").get("/teacher/exams/math-101/students/1/").content.decode()
        self.assertIn("Webcam photo", html)
        self.assertIn("Screenshot", html)

    def test_camera_unavailable_counts_towards_the_score(self):
        self.event(self.ann, self.math, "camera_unavailable", "Permission denied")
        row = self.live(self.as_user("mathteacher"))[0]
        self.assertEqual((row["score"], row["flag"]), (2, "review"))
