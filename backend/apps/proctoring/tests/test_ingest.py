import os
import uuid

from rest_framework.test import APITransactionTestCase

from apps.proctoring.models import Consent, ProctorEvent, ProctorScreenshot, StudentToken

from .helpers import IsolatedMixin, authed_client, make_exam, make_student, png


class IngestTests(IsolatedMixin, APITransactionTestCase):
    def setUp(self):
        super().setUp()
        make_exam()
        self.student = make_student()
        self.client, _ = authed_client(self.student)

    def event(self, **extra):
        body = {"exam_id": "math-101", "event_type": "tab_switch", "client_id": str(uuid.uuid4()), **extra}
        return self.client.post("/api/events/", body, format="json")

    def test_event_created_with_identity_from_token(self):
        res = self.event(student="Mallory (666)")  # spoofed body field must be ignored
        self.assertEqual(res.status_code, 201)
        self.assertEqual(ProctorEvent.objects.get().student, "Ann (1)")

    def test_event_detail_is_stored_and_optional(self):
        self.assertEqual(self.event(event_type="blocked_app_detected", detail="OBS").status_code, 201)
        self.assertEqual(self.event().status_code, 201)
        self.assertEqual(sorted(ProctorEvent.objects.values_list("detail", flat=True)), ["", "OBS"])

    def test_event_detail_length_is_limited(self):
        self.assertEqual(self.event(detail="x" * 201).status_code, 400)
        self.assertFalse(ProctorEvent.objects.exists())

    def test_event_happy_path_query_count(self):
        body = {"exam_id": "math-101", "event_type": "tab_switch", "client_id": str(uuid.uuid4())}
        with self.assertNumQueries(3):  # token+student, exam lookup, insert
            self.client.post("/api/events/", body, format="json")

    def test_event_retry_is_idempotent(self):
        cid = str(uuid.uuid4())
        first = self.event(client_id=cid)
        second = self.event(client_id=cid)
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(ProctorEvent.objects.count(), 1)

    def test_client_id_of_another_student_conflicts(self):
        cid = str(uuid.uuid4())
        self.event(client_id=cid)
        other_client, _ = authed_client(make_student(roll="2", name="Bob", email="b@example.com"))
        res = other_client.post(
            "/api/events/", {"exam_id": "math-101", "event_type": "tab_switch", "client_id": cid}, format="json"
        )
        self.assertEqual(res.status_code, 409)
        self.assertEqual(ProctorEvent.objects.count(), 1)

    def test_events_without_client_id_are_not_deduplicated(self):
        body = {"exam_id": "math-101", "event_type": "tab_switch"}
        self.client.post("/api/events/", body, format="json")
        self.client.post("/api/events/", body, format="json")
        self.assertEqual(ProctorEvent.objects.count(), 2)

    def test_unknown_exam_rejected(self):
        res = self.client.post("/api/events/", {"exam_id": "nope", "event_type": "x"}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_consent_created(self):
        res = self.client.post("/api/consent/", {"exam_id": "math-101"}, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Consent.objects.get().student, "Ann (1)")

    def test_screenshot_upload_and_query_count(self):
        body = {"exam_id": "math-101", "file": png(), "client_id": str(uuid.uuid4())}
        with self.assertNumQueries(3):
            res = self.client.post("/api/screenshots/", body, format="multipart")
        self.assertEqual(res.status_code, 201)
        shot = ProctorScreenshot.objects.get()
        self.assertEqual(shot.student, "Ann (1)")
        self.assertTrue(os.path.exists(shot.file.path))

    def test_screenshot_retry_is_idempotent_and_leaves_no_orphan_file(self):
        cid = str(uuid.uuid4())
        for expected in (201, 200):
            res = self.client.post(
                "/api/screenshots/", {"exam_id": "math-101", "file": png(), "client_id": cid}, format="multipart"
            )
            self.assertEqual(res.status_code, expected)
        self.assertEqual(ProctorScreenshot.objects.count(), 1)
        stored = [f for _, _, files in os.walk(self._media) for f in files]
        self.assertEqual(len(stored), 1)

    def test_screenshot_rejects_non_images(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        bad = SimpleUploadedFile("x.html", b"<script>", content_type="text/html")
        res = self.client.post("/api/screenshots/", {"exam_id": "math-101", "file": bad}, format="multipart")
        self.assertEqual(res.status_code, 400)
        self.assertFalse(ProctorScreenshot.objects.exists())

    def test_heartbeat_updates_last_seen_with_two_queries(self):
        with self.assertNumQueries(2):  # auth lookup + update
            res = self.client.post("/api/heartbeat/")
        self.assertEqual(res.status_code, 200)
        self.assertIsNotNone(StudentToken.objects.get().last_seen_at)


class WebcamIngestTests(IsolatedMixin, APITransactionTestCase):
    def setUp(self):
        super().setUp()
        make_exam()
        self.client, _ = authed_client(make_student())

    def upload(self, **extra):
        from django.core.files.uploadedfile import SimpleUploadedFile

        photo = SimpleUploadedFile("w.jpg", b"\xff\xd8\xff\xe0fake", content_type="image/jpeg")
        return self.client.post(
            "/api/screenshots/", {"exam_id": "math-101", "file": photo, "client_id": str(uuid.uuid4()), **extra}, format="multipart"
        )

    def test_webcam_jpeg_is_stored_with_its_kind(self):
        self.assertEqual(self.upload(kind="webcam").status_code, 201)
        self.assertEqual(ProctorScreenshot.objects.get().kind, "webcam")

    def test_kind_defaults_to_screen(self):
        self.upload()
        self.assertEqual(ProctorScreenshot.objects.get().kind, "screen")

    def test_unknown_kind_is_rejected(self):
        self.assertEqual(self.upload(kind="microphone").status_code, 400)
        self.assertFalse(ProctorScreenshot.objects.exists())

    def test_jpeg_screen_captures_are_accepted_like_webcam_photos(self):
        res = self.upload()  # kind defaults to "screen"; the desktop app now sends compressed JPEGs
        self.assertEqual(res.status_code, 201)
        shot = ProctorScreenshot.objects.get()
        self.assertEqual(shot.kind, "screen")
        self.assertTrue(shot.file.name.endswith(".jpg"))
