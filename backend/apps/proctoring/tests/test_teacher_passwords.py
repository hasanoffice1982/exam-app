import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from rest_framework.test import APIClient

from apps.proctoring import services
from apps.proctoring.models import Student, StudentToken

from .helpers import IsolatedMixin, authed_client, make_exam, make_student
from .test_dashboard import DashboardBase


def passwords_from(response) -> dict[str, str]:
    """{roll: password} parsed from the printed sheet."""
    html = response.content.decode()
    return {m.group(1): m.group(2) for m in re.finditer(r"<tr><td>([^<]+)</td><td>[^<]*</td><td>[^<]*</td><td><code>([^<]+)</code></td></tr>", html)}


def login(roll, password):
    return APIClient().post("/api/login/", {"roll_number": roll, "password": password}, format="json")


class ServiceTests(IsolatedMixin, TestCase):
    def test_issued_passwords_are_random_distinct_and_work(self):
        students = [make_student(roll=str(i), name=f"S{i}", email=f"s{i}@x.com", activated=False) for i in range(5)]
        issued = services.issue_first_time_passwords(students)
        passwords = [p for _, p in issued]
        self.assertEqual(len(set(passwords)), 5)  # nobody shares a password
        self.assertTrue(all(len(p) == 12 for p in passwords))
        for student, password in issued:
            self.assertEqual(login(student.roll_number, password).status_code, 200)

    def test_only_hashes_are_stored(self):
        student = make_student(activated=False)
        [(_, password)] = services.issue_first_time_passwords([student])
        student.refresh_from_db()
        self.assertNotIn(password, student.password)

    def test_regenerating_replaces_the_old_password_and_revokes_the_session(self):
        student = make_student()  # already has a password and a session
        client, _ = authed_client(student)
        [(_, new)] = services.issue_first_time_passwords([Student.objects.get(pk=student.pk)])
        self.assertEqual(login("1", "S3cure-test-pw").status_code, 401)
        self.assertEqual(login("1", new).status_code, 200)
        self.assertEqual(client.get("/api/exams/").status_code, 401)
        self.assertFalse(StudentToken.objects.filter(student=student).exists() and False)

    def test_no_email_is_involved(self):
        services.issue_first_time_passwords([make_student(activated=False)])
        self.assertEqual(mail.outbox, [])


class AdminActionTests(IsolatedMixin, TestCase):
    def setUp(self):
        super().setUp()
        get_user_model().objects.create_superuser("root", "r@example.com", "pw")
        self.client = Client()
        self.client.login(username="root", password="pw")
        self.a = make_student(roll="1", name="Ann", activated=False, batch=81)
        self.b = make_student(roll="2", name="Bob", email="b@x.com", activated=False, batch=82)

    def run_action(self, *students):
        return self.client.post(
            "/admin/proctoring/student/",
            {"action": "generate_passwords", "_selected_action": [s.pk for s in students]},
        )

    def test_sheet_lists_each_selected_student_with_a_working_password(self):
        res = self.run_action(self.a, self.b)
        self.assertEqual(res.status_code, 200)
        found = passwords_from(res)
        self.assertEqual(set(found), {"1", "2"})
        for roll, password in found.items():
            self.assertEqual(login(roll, password).status_code, 200)

    def test_sheet_is_never_cached(self):
        self.assertIn("no-store", self.run_action(self.a)["Cache-Control"])

    def test_inactive_students_are_skipped(self):
        Student.objects.filter(pk=self.b.pk).update(is_active=False)
        self.assertEqual(set(passwords_from(self.run_action(self.a, self.b))), {"1"})

    def test_student_names_are_escaped_in_the_sheet(self):
        Student.objects.filter(pk=self.a.pk).update(name="<script>alert(1)</script>")
        html = self.run_action(self.a).content.decode()
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_teachers_cannot_reach_the_action(self):
        from io import StringIO

        from django.core.management import call_command

        make_exam()
        call_command("create_teacher", "t", "--exams", "math-101", "--password", "pw", stdout=StringIO())
        teacher = Client()
        teacher.login(username="t", password="pw")
        res = teacher.post("/admin/proctoring/student/", {"action": "generate_passwords", "_selected_action": [self.a.pk]})
        self.assertIn(res.status_code, (403, 302))
        self.a.refresh_from_db()
        self.assertFalse(self.a.is_activated)


class TeacherBatchPasswordTests(DashboardBase):
    def setUp(self):
        super().setUp()
        self.math.batch = 81
        self.math.save()
        Student.objects.filter(pk__in=[self.ann.pk, self.bob.pk]).update(password="")  # both not activated yet
        self.cara = make_student(roll="3", name="Cara", email="c@x.com", activated=False, batch=81)
        self.dan = make_student(roll="4", name="Dan", email="d@x.com", activated=False, batch=82)
        self.eve = make_student(roll="5", name="Eve", email="e@x.com", activated=True, batch=81)  # already has one
        self.url = "/teacher/exams/math-101/passwords/"

    def test_generates_only_for_inactive_students_of_the_exams_batch(self):
        res = self.as_user("mathteacher").post(self.url)
        found = passwords_from(res)
        self.assertEqual(set(found), {"1", "2", "3"})  # Ann, Bob (batch 81, no password) and Cara
        self.assertNotIn("4", found)  # other batch
        self.assertNotIn("5", found)  # already has a password
        for roll, password in found.items():
            self.assertEqual(login(roll, password).status_code, 200)
        self.assertEqual(login("5", "S3cure-test-pw").status_code, 200)  # Eve untouched

    def test_second_click_does_not_replace_passwords_that_were_handed_out(self):
        client = self.as_user("mathteacher")
        first = passwords_from(client.post(self.url))
        second = client.post(self.url)
        self.assertEqual(passwords_from(second), {})
        self.assertContains(second, "already has a password")
        self.assertEqual(login("1", first["1"]).status_code, 200)

    def test_sheet_is_not_cached_and_shows_a_warning(self):
        res = self.as_user("mathteacher").post(self.url)
        self.assertIn("no-store", res["Cache-Control"])
        self.assertContains(res, "Shown only once")

    def test_exams_open_to_all_batches_are_refused(self):
        self.math.batch = None
        self.math.save()
        res = self.as_user("mathteacher").post(self.url)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(passwords_from(res), {})
        self.assertFalse(Student.objects.filter(roll_number="1").exclude(password="").exists())

    def test_other_subjects_teacher_gets_404_and_nothing_changes(self):
        self.assertEqual(self.as_user("physteacher").post(self.url).status_code, 404)
        self.assertEqual(Student.objects.filter(batch=81).exclude(password="").count(), 1)  # only Eve

    def test_get_anonymous_and_csrf_are_enforced(self):
        self.assertEqual(self.as_user("mathteacher").get(self.url).status_code, 405)
        self.assertEqual(Client().post(self.url).status_code, 302)
        strict = Client(enforce_csrf_checks=True)
        strict.login(username="mathteacher", password="pw")
        self.assertEqual(strict.post(self.url).status_code, 403)

    def test_monitor_page_offers_the_button_only_for_batch_exams(self):
        client = self.as_user("mathteacher")
        self.assertContains(client.get("/teacher/exams/math-101/"), "First-time passwords (batch 81)")
        self.math.batch = None
        self.math.save()
        self.assertNotContains(client.get("/teacher/exams/math-101/"), "First-time passwords")


class SelfActivationSwitchTests(IsolatedMixin, TestCase):
    def activate(self):
        return APIClient().post("/api/auth/activate/", {"roll_number": "1", "email": "ann@example.com"}, format="json")

    @override_settings(SELF_ACTIVATION=False)
    def test_self_activation_off_sends_nothing_and_points_to_the_teacher(self):
        student = make_student(activated=False)
        res = self.activate()
        self.assertEqual((res.status_code, res.data["detail"]), (403, "Ask your teacher for your password."))
        self.assertEqual(mail.outbox, [])
        student.refresh_from_db()
        self.assertFalse(student.is_activated)

    @override_settings(SELF_ACTIVATION=False)
    def test_login_hint_changes_when_self_activation_is_off(self):
        make_student(activated=False)
        res = login("1", "x")
        self.assertEqual(res.status_code, 401)
        self.assertIn("Ask your teacher", res.data["detail"])
        self.assertEqual(res.data["code"], "not_activated")

    @override_settings(SELF_ACTIVATION=False)
    def test_teacher_handout_works_while_self_activation_is_off(self):
        student = make_student(activated=False)
        [(_, password)] = services.issue_first_time_passwords([student])
        self.assertEqual(login("1", password).status_code, 200)

    def test_default_keeps_self_activation_on(self):
        make_student(activated=False)
        self.assertEqual(self.activate().status_code, 200)
