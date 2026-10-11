from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase

from apps.proctoring.models import Exam, ExamAttempt, ProctorEvent

from .helpers import authed_client, make_exam, make_student
from .test_dashboard import DashboardBase

User = get_user_model()


class TeacherAccountTests(TestCase):
    def setUp(self):
        make_exam("math-101")

    def create(self, name="t", exams="math-101", *extra):
        out = StringIO()
        call_command("create_teacher", name, "--exams", exams, "--password", "pw", *extra, stdout=out)
        return User.objects.get(username=name)

    def test_teachers_are_not_staff_and_not_superusers(self):
        teacher = self.create()
        self.assertEqual((teacher.is_staff, teacher.is_superuser), (False, False))
        self.assertTrue(teacher.groups.filter(name="Teachers").exists())
        self.assertEqual(list(Exam.objects.filter(teachers=teacher).values_list("exam_id", flat=True)), ["math-101"])

    def test_rerunning_the_command_also_removes_any_admin_flag(self):
        teacher = self.create()
        User.objects.filter(pk=teacher.pk).update(is_staff=True)
        self.assertFalse(self.create().is_staff)

    def test_unknown_exam_is_rejected_and_the_command_is_repeatable(self):
        with self.assertRaises(CommandError):
            self.create("x", "nope")
        make_exam("physics-101")
        self.create("t", "physics-101")
        teacher = self.create("t", "math-101")
        self.assertEqual(sorted(Exam.objects.filter(teachers=teacher).values_list("exam_id", flat=True)), ["math-101", "physics-101"])


class TeachersCannotUseTheAdminSite(TestCase):
    def setUp(self):
        make_exam("math-101")
        call_command("create_teacher", "t", "--exams", "math-101", "--password", "pw", stdout=StringIO())

    def test_admin_login_refuses_a_teacher(self):
        res = Client().post("/admin/login/", {"username": "t", "password": "pw", "next": "/admin/"})
        self.assertEqual(res.status_code, 200)  # form redisplayed with an error, no redirect into the admin
        self.assertNotIn("sessionid", res.cookies)

    def test_a_signed_in_teacher_is_bounced_from_every_admin_page(self):
        client = Client()
        client.login(username="t", password="pw")
        for url in ("/admin/", "/admin/proctoring/exam/", "/admin/proctoring/student/", "/admin/auth/user/", "/admin/proctoring/proctorscreenshot/"):
            res = client.get(url)
            self.assertEqual(res.status_code, 302, url)
            self.assertIn("/admin/login/", res["Location"], url)

    def test_a_superuser_can_use_the_admin(self):
        User.objects.create_superuser("root", "r@example.com", "pw")
        client = Client()
        client.login(username="root", password="pw")
        self.assertEqual(client.get("/admin/proctoring/exam/").status_code, 200)

    def test_admin_index_does_not_link_to_the_teacher_dashboard(self):
        User.objects.create_superuser("root", "r@example.com", "pw")
        client = Client()
        client.login(username="root", password="pw")
        self.assertNotContains(client.get("/admin/"), 'href="/teacher/')


class TeacherLoginTests(TestCase):
    def setUp(self):
        make_exam("math-101")
        call_command("create_teacher", "t", "--exams", "math-101", "--password", "pw", stdout=StringIO())
        User.objects.create_superuser("root", "r@example.com", "pw-root")
        User.objects.create_user("plain", password="pw", is_staff=True)  # staff but not a teacher

    def login(self, username="t", password="pw", client=None, **extra):
        return (client or Client()).post("/teacher/login/", {"username": username, "password": password, **extra})

    def test_login_page_is_public_and_standalone(self):
        res = Client().get("/teacher/login/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Teacher log in")
        self.assertNotContains(res, "/admin/")

    def test_a_teacher_logs_in_and_lands_on_the_dashboard(self):
        client = Client()
        res = self.login(client=client)
        self.assertRedirects(res, "/teacher/", fetch_redirect_response=False)
        self.assertEqual(client.get("/teacher/").status_code, 200)

    def test_wrong_password_shows_an_error(self):
        res = self.login(password="nope")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Please enter a correct username and password")

    def test_five_wrong_passwords_lock_the_account_even_for_the_right_one(self):
        from django.core.cache import cache

        cache.clear()
        for _ in range(5):
            self.login(password="nope")
        res = self.login()
        self.assertContains(res, "Too many failed attempts")
        self.assertNotIn("sessionid", res.cookies)
        cache.clear()

    def test_success_resets_the_failure_counter(self):
        from django.core.cache import cache

        cache.clear()
        for _ in range(4):
            self.login(password="nope")
        self.assertEqual(self.login().status_code, 302)
        for _ in range(4):
            self.login(password="nope")
        self.assertEqual(self.login().status_code, 302)  # not locked: the counter restarted
        cache.clear()

    def test_accounts_that_are_not_teachers_cannot_log_in(self):
        res = self.login("plain")
        self.assertContains(res, "not a teacher account")
        self.assertNotIn("sessionid", res.cookies)

    def test_the_super_admin_can_log_in_here_and_sees_every_exam(self):
        make_exam("physics-101")
        client = Client()
        self.assertEqual(self.login("root", "pw-root", client=client).status_code, 302)
        res = client.get("/teacher/")
        self.assertContains(res, "math-101")
        self.assertContains(res, "physics-101")

    def test_next_is_followed_only_inside_this_site(self):
        ok = self.login(next="/teacher/exams/math-101/")
        self.assertEqual(ok["Location"], "/teacher/exams/math-101/")
        evil = self.login(next="https://evil.example/steal")
        self.assertEqual(evil["Location"], "/teacher/")

    def test_signed_in_users_skip_the_login_page(self):
        client = Client()
        self.login(client=client)
        self.assertRedirects(client.get("/teacher/login/"), "/teacher/", fetch_redirect_response=False)

    def test_logout_needs_post_and_ends_the_session(self):
        client = Client()
        self.login(client=client)
        self.assertEqual(client.get("/teacher/logout/").status_code, 405)
        res = client.post("/teacher/logout/")
        self.assertRedirects(res, "/teacher/login/", fetch_redirect_response=False)
        self.assertEqual(client.get("/teacher/").status_code, 302)


class SeparationInTheMarkupTests(DashboardBase):
    def test_teacher_pages_never_link_to_the_admin(self):
        client = self.as_user("mathteacher")
        self.event(self.ann, self.math, "tab_switch")
        pages = [
            "/teacher/", "/teacher/exams/math-101/", "/teacher/exams/math-101/settings/",
            "/teacher/exams/math-101/marks/", "/teacher/exams/math-101/students/1/",
        ]
        for url in pages:
            res = client.get(url)
            self.assertEqual(res.status_code, 200, url)
            self.assertNotContains(res, "/admin", msg_prefix=url)

    def test_the_super_admin_sees_everything_in_the_dashboard(self):
        client = Client()
        client.login(username="root", password="pw")
        self.assertContains(client.get("/teacher/"), "physics-101")
        for exam in ("math-101", "physics-101"):
            self.assertEqual(client.get(f"/teacher/exams/{exam}/").status_code, 200)
            self.assertEqual(client.get(f"/teacher/exams/{exam}/live.json").status_code, 200)
        self.assertEqual(client.get("/teacher/exams/physics-101/students/2/").status_code, 200)


class ExamSettingsTests(DashboardBase):
    url = "/teacher/exams/math-101/settings/"

    def payload(self, **over):
        data = {
            "written_enabled": "on", "form_url": "https://example.com/new-form", "practical_screenshot_seconds": 60,
            "grace_seconds": 5, "monitoring_enabled": "on", "webcam_interval_seconds": 180, "starts_at": "", "ends_at": "",
        }
        data.update(over)
        return {k: v for k, v in data.items() if v is not None}

    def test_form_shows_the_teachers_fields_and_not_the_admin_only_ones(self):
        res = self.as_user("mathteacher").get(self.url)
        for field in ("written_enabled", "form_url", "practical_enabled", "practical_instructions", "practical_url",
                      "practical_screenshot_seconds", "starts_at", "ends_at", "grace_seconds", "monitoring_enabled",
                      "webcam_enabled", "webcam_interval_seconds"):
            self.assertContains(res, f'name="{field}"')
        for locked in ("exam_id", "name", "batch", "teachers"):
            self.assertNotContains(res, f'name="{locked}"')

    def test_saving_updates_the_exam_and_confirms(self):
        res = self.as_user("mathteacher").post(self.url, self.payload(grace_seconds=9, starts_at="2026-10-12T09:30", ends_at="2026-10-12T11:00", webcam_enabled="on"))
        self.assertRedirects(res, f"{self.url}?saved=1", fetch_redirect_response=False)
        self.math.refresh_from_db()
        self.assertEqual((self.math.grace_seconds, self.math.webcam_enabled, self.math.form_url), (9, True, "https://example.com/new-form"))
        self.assertEqual((self.math.starts_at.hour, self.math.starts_at.minute, self.math.ends_at.hour), (9, 30, 11))
        self.assertContains(self.as_user("mathteacher").get(f"{self.url}?saved=1"), "Saved")

    def test_the_teacher_can_switch_on_the_practical_part(self):
        res = self.as_user("mathteacher").post(self.url, self.payload(practical_enabled="on", practical_instructions="Build it"))
        self.assertEqual(res.status_code, 302)
        self.math.refresh_from_db()
        self.assertTrue(self.math.practical_enabled)

    def test_validation_errors_are_shown_and_nothing_is_saved(self):
        client = self.as_user("mathteacher")
        cases = [
            (self.payload(ends_at="2026-10-12T08:00", starts_at="2026-10-12T09:00"), "end time must be after"),
            (self.payload(form_url=""), "needs a Google Form link"),
            (self.payload(practical_enabled="on"), "needs instructions or a link"),
            (self.payload(written_enabled=None), "Turn on the written part"),
            (self.payload(practical_screenshot_seconds=5), "greater than or equal to 15"),
            (self.payload(webcam_interval_seconds=10), "greater than or equal to 30"),
            (self.payload(form_url="not a url"), "valid URL"),
        ]
        for data, message in cases:
            res = client.post(self.url, data)
            self.assertEqual(res.status_code, 200, message)
            self.assertContains(res, message)
        self.math.refresh_from_db()
        self.assertEqual(self.math.grace_seconds, 3)

    def test_crafted_posts_cannot_change_the_admin_only_fields(self):
        before = (self.math.name, self.math.batch, self.math.exam_id)
        self.as_user("mathteacher").post(self.url, self.payload(name="Hacked", batch=999, exam_id="hacked", teachers="1"))
        self.math.refresh_from_db()
        self.assertEqual((self.math.name, self.math.batch, self.math.exam_id), before)
        self.assertEqual(list(self.math.teachers.values_list("username", flat=True)), ["mathteacher"])

    def test_other_subjects_teacher_gets_404_and_nothing_changes(self):
        client = self.as_user("physteacher")
        self.assertEqual(client.get(self.url).status_code, 404)
        self.assertEqual(client.post(self.url, self.payload(grace_seconds=9)).status_code, 404)
        self.math.refresh_from_db()
        self.assertEqual(self.math.grace_seconds, 3)

    def test_anonymous_and_csrf(self):
        self.assertRedirects(Client().get(self.url), f"/teacher/login/?next={self.url}", fetch_redirect_response=False)
        strict = Client(enforce_csrf_checks=True)
        strict.login(username="mathteacher", password="pw")
        self.assertEqual(strict.post(self.url, self.payload(grace_seconds=9)).status_code, 403)
        self.math.refresh_from_db()
        self.assertEqual(self.math.grace_seconds, 3)

    def test_the_super_admin_can_edit_any_exam(self):
        client = Client()
        client.login(username="root", password="pw")
        res = client.post("/teacher/exams/physics-101/settings/", self.payload(grace_seconds=7))
        self.assertEqual(res.status_code, 302)
        self.phys.refresh_from_db()
        self.assertEqual(self.phys.grace_seconds, 7)

    def test_monitor_page_links_to_the_settings(self):
        self.assertContains(self.as_user("mathteacher").get("/teacher/exams/math-101/"), 'href="/teacher/exams/math-101/settings/"')


class AdminAttemptActionsTests(TestCase):
    """Force end and reset still exist in the admin for the super admin (teachers use the dashboard buttons)."""

    def setUp(self):
        self.exam = make_exam("math-101")
        self.student = make_student()
        self.attempt = ExamAttempt.objects.create(student=self.student, exam=self.exam)
        User.objects.create_superuser("root", "r@example.com", "pw")
        self.client = Client()
        self.client.login(username="root", password="pw")

    def run_action(self, action):
        return self.client.post("/admin/proctoring/examattempt/", {"action": action, "_selected_action": [self.attempt.pk]}, follow=True)

    def test_force_end_from_the_admin(self):
        api_client, _ = authed_client(self.student)
        self.run_action("force_end")
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, "force_ended")
        self.assertEqual(api_client.get("/api/exams/").status_code, 401)
        self.assertEqual(ProctorEvent.objects.get(event_type="force_ended").detail, "root")

    def test_reset_from_the_admin(self):
        self.run_action("reset_attempt")
        self.assertFalse(ExamAttempt.objects.filter(pk=self.attempt.pk).exists())
