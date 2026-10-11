import re

from django.test import Client, TestCase, override_settings


class HomeTests(TestCase):
    def test_home_is_public_and_only_offers_the_teacher_login(self):
        res = Client().get("/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'href="/teacher/"')
        self.assertContains(res, "Teacher log in")
        self.assertNotContains(res, "/admin/")  # nothing on the public page advertises the admin site

    def test_home_shows_username_and_logout_when_signed_in(self):
        from django.contrib.auth import get_user_model

        get_user_model().objects.create_superuser("root", "r@example.com", "pw")
        client = Client()
        client.login(username="root", password="pw")
        res = client.get("/")
        self.assertContains(res, "root")
        self.assertContains(res, "Log out")

    def test_download_link_only_when_configured(self):
        self.assertNotContains(Client().get("/"), "Download the student app")
        with override_settings(STUDENT_DOWNLOAD_URL_MAC="https://drive.google.com/file/d/abc/view"):
            res = Client().get("/")
        self.assertContains(res, "Download the student app (Mac)")
        self.assertContains(res, "https://drive.google.com/file/d/abc/view")

    def test_unsafe_download_urls_are_ignored(self):
        for bad in ("javascript:alert(1)", "data:text/html,x", "//evil.example/x"):
            with override_settings(STUDENT_DOWNLOAD_URL_MAC=bad):
                self.assertNotContains(Client().get("/"), "Download the student app")

    def test_home_exposes_no_data_and_only_allows_get(self):
        self.assertEqual(Client().post("/").status_code, 405)
        html = Client().get("/").content.decode().lower()
        body = re.sub(r"<style.*?</style>", "", html, flags=re.S)  # CSS contains words like "scroll"
        for secret in ("roll number", "password", "token", "student ("):
            self.assertNotIn(secret, body)
