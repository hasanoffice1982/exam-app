from datetime import timedelta

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from .helpers import IsolatedMixin, authed_client, make_exam, make_student


class ConfigTests(IsolatedMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.exam = make_exam()
        self.client, _ = authed_client(make_student())

    def test_get_config_shape_and_query_count(self):
        with self.assertNumQueries(2):  # auth, exam
            res = self.client.get("/api/config/math-101/")
        self.assertEqual(res.status_code, 200)
        for key in ("monitoring_enabled", "form_url", "mode", "starts_at", "ends_at", "grace_seconds", "status", "server_time"):
            self.assertIn(key, res.data)
        self.assertEqual(res.data["grace_seconds"], 3)

    def test_unknown_exam_404(self):
        self.assertEqual(self.client.get("/api/config/nope/").status_code, 404)

    def test_status_follows_schedule(self):
        now = timezone.now()
        cases = {
            "upcoming": dict(starts_at=now + timedelta(hours=1)),
            "closed": dict(ends_at=now - timedelta(minutes=1)),
            "open": dict(starts_at=now - timedelta(hours=1), ends_at=now + timedelta(hours=1)),
        }
        for expected, fields in cases.items():
            for k, v in fields.items():
                setattr(self.exam, k, v)
            self.exam.save()
            self.assertEqual(self.client.get("/api/config/math-101/").data["status"], expected)
            self.exam.starts_at = self.exam.ends_at = None

    def test_student_cannot_change_config(self):
        res = self.client.post("/api/config/math-101/", {"monitoring_enabled": False}, format="json")
        self.assertIn(res.status_code, (401, 403))
        self.exam.refresh_from_db()
        self.assertTrue(self.exam.monitoring_enabled)

    def test_anonymous_cannot_change_config(self):
        res = APIClient().post("/api/config/math-101/", {"monitoring_enabled": False}, format="json")
        self.assertIn(res.status_code, (401, 403))

    @override_settings(ADMIN_API_KEY="")
    def test_admin_write_disabled_without_configured_key(self):
        res = APIClient().post(
            "/api/config/math-101/", {"monitoring_enabled": False}, format="json", HTTP_X_ADMIN_KEY=""
        )
        self.assertIn(res.status_code, (401, 403))

    @override_settings(ADMIN_API_KEY="sekret")
    def test_admin_key_toggles_monitoring(self):
        admin = APIClient()
        bad = admin.post("/api/config/math-101/", {"monitoring_enabled": False}, format="json", HTTP_X_ADMIN_KEY="wrong")
        self.assertIn(bad.status_code, (401, 403))
        ok = admin.post("/api/config/math-101/", {"monitoring_enabled": False}, format="json", HTTP_X_ADMIN_KEY="sekret")
        self.assertEqual(ok.status_code, 200)
        self.exam.refresh_from_db()
        self.assertFalse(self.exam.monitoring_enabled)

    @override_settings(ADMIN_API_KEY="sekret")
    def test_end_before_start_rejected(self):
        now = timezone.now()
        body = {"starts_at": now.isoformat(), "ends_at": (now - timedelta(hours=1)).isoformat()}
        res = APIClient().post("/api/config/math-101/", body, format="json", HTTP_X_ADMIN_KEY="sekret")
        self.assertEqual(res.status_code, 400)


class WebcamConfigTests(IsolatedMixin, APITestCase):
    def setUp(self):
        super().setUp()
        make_exam()
        self.client, _ = authed_client(make_student())

    def test_webcam_settings_have_safe_defaults(self):
        data = self.client.get("/api/config/math-101/").data
        self.assertEqual((data["webcam_enabled"], data["webcam_interval_seconds"]), (False, 180))

    @override_settings(ADMIN_API_KEY="k")
    def test_admin_can_enable_and_tune_webcam(self):
        res = APIClient().post(
            "/api/config/math-101/", {"webcam_enabled": True, "webcam_interval_seconds": 60}, format="json", HTTP_X_ADMIN_KEY="k"
        )
        self.assertEqual(res.status_code, 200)
        data = self.client.get("/api/config/math-101/").data
        self.assertEqual((data["webcam_enabled"], data["webcam_interval_seconds"]), (True, 60))

    @override_settings(ADMIN_API_KEY="k")
    def test_interval_limits_are_enforced(self):
        for bad in (5, 29, 3601):
            res = APIClient().post("/api/config/math-101/", {"webcam_interval_seconds": bad}, format="json", HTTP_X_ADMIN_KEY="k")
            self.assertEqual(res.status_code, 400, bad)
