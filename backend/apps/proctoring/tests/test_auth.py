from datetime import timedelta
from unittest import mock

from django.utils import timezone
from django.core import mail
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient, APITestCase
from rest_framework.throttling import ScopedRateThrottle

from apps.proctoring.models import StudentToken
from apps.proctoring.throttles import HONEYPOT_FIELD

from .helpers import PASSWORD, IsolatedMixin, authed_client, make_exam, make_student

LOGIN = "/api/login/"
ACTIVATE = "/api/auth/activate/"


class LoginTests(IsolatedMixin, APITestCase):
    def test_login_returns_profile_and_token(self):
        make_student()
        res = self.client.post(LOGIN, {"roll_number": "1", "password": PASSWORD}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["name"], "Ann")
        self.assertTrue(res.data["token"])
        self.assertNotIn(res.data["token"], StudentToken.objects.get().key_hash)  # only a hash is stored

    def test_wrong_password_is_generic_401(self):
        make_student()
        res = self.client.post(LOGIN, {"roll_number": "1", "password": "nope"}, format="json")
        self.assertEqual(res.status_code, 401)
        unknown = self.client.post(LOGIN, {"roll_number": "999", "password": "nope"}, format="json")
        self.assertEqual(res.data["detail"], unknown.data["detail"])  # no user enumeration

    def test_not_activated_student_gets_hint(self):
        make_student(activated=False)
        res = self.client.post(LOGIN, {"roll_number": "1", "password": "x"}, format="json")
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.data["code"], "not_activated")

    def test_roll_lockout_after_five_failures(self):
        make_student()
        for _ in range(5):
            self.client.post(LOGIN, {"roll_number": "1", "password": "bad"}, format="json")
        res = self.client.post(LOGIN, {"roll_number": "1", "password": PASSWORD}, format="json")
        self.assertEqual(res.status_code, 429)

    def test_ip_rate_limit(self):
        with mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"auth": "2/min"}):
            codes = [
                self.client.post(LOGIN, {"roll_number": "1", "password": "x"}, format="json").status_code
                for _ in range(3)
            ]
        self.assertEqual(codes, [401, 401, 429])

    def test_honeypot_trips_and_blocks_ip(self):
        make_student()
        body = {"roll_number": "1", "password": PASSWORD, HONEYPOT_FIELD: "http://spam"}
        res = self.client.post(LOGIN, body, format="json")
        self.assertEqual(res.status_code, 401)  # even valid credentials are refused
        self.assertFalse(StudentToken.objects.exists())
        follow_up = self.client.post(LOGIN, {"roll_number": "1", "password": PASSWORD}, format="json")
        self.assertEqual(follow_up.status_code, 429)  # IP now blocked

    def test_empty_honeypot_is_fine(self):
        make_student()
        body = {"roll_number": "1", "password": PASSWORD, HONEYPOT_FIELD: ""}
        self.assertEqual(self.client.post(LOGIN, body, format="json").status_code, 200)


class ActivateTests(IsolatedMixin, APITestCase):
    def activate(self, roll="1", email="ann@example.com", **extra):
        return self.client.post(ACTIVATE, {"roll_number": roll, "email": email, **extra}, format="json")

    def emailed_password(self):
        import re

        self.assertEqual(len(mail.outbox), 1)
        match = re.search(r"Password:\s+(\S+)", mail.outbox[0].body)
        self.assertIsNotNone(match)
        return match.group(1)

    def test_password_is_emailed_to_the_registered_address_not_returned(self):
        make_student(activated=False)
        res = self.activate(email="ANN@example.com")  # case-insensitive match
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["email"], "a***@example.com")
        self.assertNotIn("password", res.data)
        self.assertNotIn("token", res.data)
        self.assertEqual(mail.outbox[0].to, ["ann@example.com"])
        self.assertEqual(len(self.emailed_password()), 12)

    def test_the_emailed_password_logs_in(self):
        make_student(activated=False)
        self.activate()
        login = self.client.post(LOGIN, {"roll_number": "1", "password": self.emailed_password()}, format="json")
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.data["name"], "Ann")

    def test_only_a_hash_is_stored(self):
        student = make_student(activated=False)
        self.activate()
        student.refresh_from_db()
        self.assertNotIn(self.emailed_password(), student.password)
        self.assertTrue(student.password.startswith(("pbkdf2_", "argon2", "bcrypt", "scrypt")))

    def test_activating_again_is_refused_and_sends_nothing(self):
        make_student(activated=False)
        self.activate()
        mail.outbox.clear()
        res = self.activate()
        self.assertEqual(res.status_code, 409)
        self.assertEqual(mail.outbox, [])

    def test_wrong_email_or_unknown_roll_send_nothing_and_look_identical(self):
        make_student(activated=False)
        wrong = self.activate(email="x@example.com")
        unknown = self.activate(roll="999")
        self.assertEqual((wrong.status_code, unknown.status_code), (400, 400))
        self.assertEqual(wrong.data["detail"], unknown.data["detail"])  # no roll enumeration
        self.assertEqual(mail.outbox, [])

    def test_wrong_email_attempts_lock_out(self):
        make_student(activated=False)
        for _ in range(5):
            self.assertEqual(self.activate(email="x@example.com").status_code, 400)
        res = self.activate()
        self.assertEqual(res.status_code, 429)
        self.assertEqual(mail.outbox, [])

    def test_send_failure_leaves_the_account_inactive_so_the_student_can_retry(self):
        student = make_student(activated=False)
        with mock.patch("apps.proctoring.services.send_mail", side_effect=OSError("smtp down")):
            res = self.activate()
        self.assertEqual(res.status_code, 503)
        student.refresh_from_db()
        self.assertFalse(student.is_activated)
        self.assertEqual(self.activate().status_code, 200)  # works once email is back
        self.assertEqual(len(mail.outbox), 1)

    def test_student_without_email_cannot_activate(self):
        make_student(activated=False, email="")
        self.assertEqual(self.activate(email="a@b.co").status_code, 400)
        self.assertEqual(mail.outbox, [])

    def test_honeypot_on_activate_sends_nothing(self):
        make_student(activated=False)
        res = self.activate(**{HONEYPOT_FIELD: "x"})
        self.assertEqual(res.status_code, 401)
        self.assertEqual(mail.outbox, [])
        self.assertFalse(StudentToken.objects.exists())

    def test_email_body_contains_roll_and_instructions(self):
        make_student(activated=False)
        self.activate()
        body = mail.outbox[0].body
        self.assertIn("Roll number: 1", body)
        self.assertIn("Ann", body)
        self.assertEqual(mail.outbox[0].subject, "Your ExamProctor password")


class EmailCheckTests(SimpleTestCase):
    def test_warns_when_production_would_print_passwords_to_the_console(self):
        from apps.proctoring.checks import email_backend_check

        console = "django.core.mail.backends.console.EmailBackend"
        with override_settings(DEBUG=False, EMAIL_BACKEND=console):
            self.assertEqual([w.id for w in email_backend_check(None)], ["proctoring.W001"])
        with override_settings(DEBUG=True, EMAIL_BACKEND=console):
            self.assertEqual(email_backend_check(None), [])
        with override_settings(DEBUG=False, EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend"):
            self.assertEqual(email_backend_check(None), [])

    def test_mask_email(self):
        from apps.proctoring.services import mask_email

        self.assertEqual(mask_email("ann.smith@gmail.com"), "a***@gmail.com")


class SessionTests(IsolatedMixin, APITestCase):
    PROTECTED = [("get", "/api/exams/"), ("get", "/api/config/x/"), ("post", "/api/events/"),
                 ("post", "/api/screenshots/"), ("post", "/api/consent/"), ("post", "/api/heartbeat/")]

    def test_endpoints_require_token(self):
        for method, url in self.PROTECTED:
            res = getattr(APIClient(), method)(url)
            self.assertEqual(res.status_code, 401, url)

    def test_garbage_token_rejected(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
        self.assertEqual(client.get("/api/exams/").status_code, 401)

    def test_new_login_revokes_old_session(self):
        student = make_student()
        old_client, _ = authed_client(student)
        self.assertEqual(old_client.get("/api/exams/").status_code, 200)
        new_client, _ = authed_client(student)
        self.assertEqual(old_client.get("/api/exams/").status_code, 401)
        self.assertEqual(new_client.get("/api/exams/").status_code, 200)

    def test_expired_token_rejected(self):
        client, _ = authed_client(make_student())
        StudentToken.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(client.get("/api/exams/").status_code, 401)

    def test_revoking_in_admin_ends_session(self):
        client, _ = authed_client(make_student())
        StudentToken.objects.all().delete()
        self.assertEqual(client.get("/api/exams/").status_code, 401)

    def test_deactivated_student_rejected(self):
        student = make_student()
        client, _ = authed_client(student)
        student.is_active = False
        student.save()
        self.assertEqual(client.get("/api/exams/").status_code, 401)

    def test_authenticated_exam_list_uses_two_queries(self):
        make_exam()
        client, _ = authed_client(make_student())
        with self.assertNumQueries(2):  # token+student join, exams
            client.get("/api/exams/")
