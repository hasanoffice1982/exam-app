from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.proctoring import dashboard
from apps.proctoring.models import Exam, ExamAttempt, ProctorScreenshot, Student

from .helpers import IsolatedMixin


class SeedDemoTests(IsolatedMixin, TestCase):
    def seed(self):
        call_command("seed_demo", "--force", stdout=StringIO())

    def test_refuses_to_run_against_a_database_that_is_not_marked_demo(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo", stdout=StringIO())
        self.assertFalse(Student.objects.exists())

    def test_creates_a_rich_consistent_demo(self):
        self.seed()
        self.assertEqual(Student.objects.count(), 15)
        self.assertEqual(Exam.objects.count(), 4)
        for exam in Exam.objects.all():
            exam.full_clean()  # every demo exam obeys the real rules
        physics = Exam.objects.get(exam_id="physics-mid")
        states = {r["roll_number"]: (r["status"], r["stage"], r["flag"], r["state"]) for r in dashboard.live_rows(physics)}
        self.assertEqual(states["81001"][:2], ("in_progress", "practical"))
        self.assertEqual(states["81002"][2], "flagged")
        self.assertEqual(states["81004"][3], "offline")
        self.assertEqual(states["81005"][0], "completed")
        self.assertEqual(states["81006"][0], "quit")
        self.assertEqual(states["81007"][0], "force_ended")
        self.assertEqual(states["81003"][3], "online")
        self.assertTrue(Exam.objects.get(exam_id="bio-final").archived)
        self.assertGreater(ProctorScreenshot.objects.count(), 10)

    def test_running_it_twice_gives_the_same_result(self):
        self.seed()
        counts = (Student.objects.count(), ExamAttempt.objects.count(), ProctorScreenshot.objects.count())
        self.seed()
        self.assertEqual((Student.objects.count(), ExamAttempt.objects.count(), ProctorScreenshot.objects.count()), counts)

    def test_demo_logins_work(self):
        from rest_framework.test import APIClient

        self.seed()
        api = APIClient()
        self.assertEqual(api.post("/api/login/", {"roll_number": "81003", "password": "Demo-pass-1"}, format="json").status_code, 200)
        self.assertEqual(api.post("/api/login/", {"roll_number": "81010", "password": "x"}, format="json").data["code"], "not_activated")
        from django.test import Client

        for user, password in (("admin", "Admin-demo-1"), ("rahman", "Rahman-demo-1")):
            self.assertTrue(Client().login(username=user, password=password), user)
