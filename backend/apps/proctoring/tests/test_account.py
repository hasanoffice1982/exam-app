from rest_framework.test import APIClient, APITestCase

from apps.proctoring.models import Student, StudentToken

from .helpers import PASSWORD, IsolatedMixin, authed_client, make_student

CHANGE = "/api/auth/change-password/"


class ProfileTests(IsolatedMixin, APITestCase):
    def test_profile_shows_the_students_own_details_with_a_masked_email(self):
        client, _ = authed_client(make_student(roll="42", name="Ann", email="ann.smith@gmail.com", batch=81))
        data = client.get("/api/profile/").data
        self.assertEqual(data, {"roll_number": "42", "name": "Ann", "email": "a***@gmail.com", "batch": 81})

    def test_profile_costs_one_query_and_leaks_no_secrets(self):
        client, _ = authed_client(make_student())
        with self.assertNumQueries(1):  # the session lookup that also loads the student
            res = client.get("/api/profile/")
        self.assertEqual(set(res.data), {"roll_number", "name", "email", "batch"})

    def test_students_without_batch_or_email(self):
        client, _ = authed_client(make_student(email=""))
        data = client.get("/api/profile/").data
        self.assertEqual((data["batch"], data["email"]), (None, ""))

    def test_profile_requires_a_session(self):
        self.assertEqual(APIClient().get("/api/profile/").status_code, 401)


class ChangePasswordTests(IsolatedMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.student = make_student(roll="1")
        self.client, _ = authed_client(self.student)

    def change(self, current=PASSWORD, new="a-better-pass-9"):
        return self.client.post(CHANGE, {"current_password": current, "new_password": new}, format="json")

    def login(self, password):
        return APIClient().post("/api/login/", {"roll_number": "1", "password": password}, format="json")

    def test_change_works_and_the_old_password_stops_working(self):
        self.assertEqual(self.change().status_code, 200)
        self.assertEqual(self.login(PASSWORD).status_code, 401)
        self.assertEqual(self.login("a-better-pass-9").status_code, 200)

    def test_current_session_stays_valid_and_only_a_hash_is_stored(self):
        self.change()
        self.assertEqual(self.client.get("/api/profile/").status_code, 200)
        self.student.refresh_from_db()
        self.assertNotIn("a-better-pass-9", self.student.password)

    def test_wrong_current_password_is_refused_and_changes_nothing(self):
        res = self.change(current="not-it")
        self.assertEqual((res.status_code, res.data["detail"]), (400, "Your current password is not correct."))
        self.assertEqual(self.login(PASSWORD).status_code, 200)

    def test_repeated_wrong_current_passwords_lock_out_even_the_right_one(self):
        for _ in range(5):
            self.assertEqual(self.change(current="nope").status_code, 400)
        self.assertEqual(self.change().status_code, 429)
        self.assertEqual(self.login(PASSWORD).status_code, 200)  # login itself is a separate counter

    def test_new_password_rules(self):
        res = self.change(new="short1")
        self.assertEqual(res.status_code, 400)
        self.assertIn("at least 8", res.data["detail"])
        res = self.change(new=PASSWORD)
        self.assertIn("different from the current", res.data["detail"])
        self.assertEqual(self.login(PASSWORD).status_code, 200)

    def test_new_password_cannot_be_the_roll_number(self):
        Student.objects.filter(pk=self.student.pk).update(roll_number="ROLL12345")
        res = self.client.post(CHANGE, {"current_password": PASSWORD, "new_password": "roll12345"}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("roll number", res.data["detail"])

    def test_missing_fields_and_oversized_input(self):
        self.assertEqual(self.client.post(CHANGE, {}, format="json").status_code, 400)
        self.assertEqual(self.change(new="x" * 500).status_code, 400)

    def test_requires_a_session(self):
        res = APIClient().post(CHANGE, {"current_password": PASSWORD, "new_password": "a-better-pass-9"}, format="json")
        self.assertEqual(res.status_code, 401)

    def test_a_student_can_only_change_their_own_password(self):
        other = make_student(roll="2", name="Bob", email="b@example.com")
        self.change()
        other.refresh_from_db()
        self.assertTrue(other.check_password(PASSWORD))


class LogoutTests(IsolatedMixin, APITestCase):
    def test_logout_revokes_the_session_so_a_copied_token_is_useless(self):
        student = make_student()
        client, token = authed_client(student)
        self.assertEqual(client.post("/api/auth/logout/").status_code, 200)
        self.assertFalse(StudentToken.objects.filter(student=student).exists())
        self.assertEqual(client.get("/api/profile/").status_code, 401)
        # logging in again works
        res = APIClient().post("/api/login/", {"roll_number": "1", "password": PASSWORD}, format="json")
        self.assertEqual(res.status_code, 200)

    def test_logout_without_a_session_is_refused(self):
        self.assertEqual(APIClient().post("/api/auth/logout/").status_code, 401)
