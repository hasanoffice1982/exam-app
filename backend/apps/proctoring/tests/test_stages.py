import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase
from rest_framework.test import APITransactionTestCase

from apps.proctoring import services
from apps.proctoring.models import Exam, ExamAttempt, ProctorEvent

from .helpers import IsolatedMixin, authed_client, make_exam, make_student
from .test_dashboard import DashboardBase


class ExamStageRulesTests(TestCase):
    def exam(self, **kw):
        return Exam(exam_id="x", name="X", **{"form_url": "https://example.com/form", "batch": 81, **kw})

    def test_written_only_is_the_default(self):
        e = self.exam()
        e.full_clean()
        self.assertEqual((e.written_enabled, e.practical_enabled, e.first_stage), (True, False, "written"))

    def test_both_stages_start_with_written(self):
        e = self.exam(practical_enabled=True, practical_instructions="Build the thing")
        e.full_clean()
        self.assertEqual(e.first_stage, "written")

    def test_practical_only_starts_with_practical_and_needs_no_form(self):
        e = self.exam(form_url="", written_enabled=False, practical_enabled=True, practical_url="https://example.com/task")
        e.full_clean()
        self.assertEqual(e.first_stage, "practical")

    def test_every_exam_needs_exactly_one_batch(self):
        with self.assertRaises(ValidationError) as ctx:
            self.exam(batch=None).full_clean()
        self.assertIn("batch", ctx.exception.message_dict)

    def test_at_least_one_stage_is_required(self):
        with self.assertRaises(ValidationError) as ctx:
            self.exam(written_enabled=False).full_clean()
        self.assertIn("written_enabled", ctx.exception.message_dict)

    def test_written_part_needs_a_form_link(self):
        with self.assertRaises(ValidationError) as ctx:
            self.exam(form_url="").full_clean()
        self.assertIn("form_url", ctx.exception.message_dict)

    def test_practical_part_needs_instructions_or_a_link(self):
        with self.assertRaises(ValidationError) as ctx:
            self.exam(practical_enabled=True).full_clean()
        self.assertIn("practical_instructions", ctx.exception.message_dict)
        self.exam(practical_enabled=True, practical_url="https://example.com/t").full_clean()

    def test_practical_screenshot_interval_limits(self):
        for bad in (5, 14, 601):
            with self.assertRaises(ValidationError):
                self.exam(practical_screenshot_seconds=bad).full_clean()


class StageApiTests(IsolatedMixin, APITransactionTestCase):
    def setUp(self):
        super().setUp()
        self.both = make_exam("both", practical_enabled=True, practical_instructions="Do the lab")
        self.written = make_exam("written")
        self.practical = make_exam("practical", written_enabled=False, practical_enabled=True, practical_url="https://example.com/t", form_url="")
        self.student = make_student()
        self.client, _ = authed_client(self.student)

    def start(self, exam_id):
        return self.client.post(f"/api/exams/{exam_id}/start/")

    def advance(self, exam_id):
        return self.client.post(f"/api/exams/{exam_id}/advance/")

    def stage(self, exam_id):
        return ExamAttempt.objects.get(exam__exam_id=exam_id).stage

    def test_each_exam_starts_in_its_first_stage(self):
        self.assertEqual(self.start("both").data["stage"], "written")
        self.assertEqual(self.start("written").data["stage"], "written")
        self.assertEqual(self.start("practical").data["stage"], "practical")

    def test_config_exposes_the_practical_settings(self):
        data = self.start("both").data
        self.assertEqual((data["written_enabled"], data["practical_enabled"]), (True, True))
        self.assertEqual((data["practical_instructions"], data["practical_screenshot_seconds"]), ("Do the lab", 60))

    def test_written_then_practical_in_that_order(self):
        self.start("both")
        res = self.advance("both")
        self.assertEqual((res.status_code, res.data["stage"]), (200, "practical"))
        self.assertEqual(self.stage("both"), "practical")

    def test_resume_after_a_crash_returns_to_the_current_stage(self):
        self.start("both")
        self.advance("both")
        self.assertEqual(self.start("both").data["stage"], "practical")  # cannot be sent back to the written part

    def test_advance_is_idempotent_and_logged_once(self):
        self.start("both")
        self.advance("both")
        self.assertEqual(self.advance("both").status_code, 200)
        events = ProctorEvent.objects.filter(event_type="stage_advanced")
        self.assertEqual(events.count(), 1)
        self.assertEqual(events.get().detail, "written->practical by student")

    def test_no_practical_part_means_no_advance(self):
        self.start("written")
        res = self.advance("written")
        self.assertEqual((res.status_code, res.data["detail"]), (400, "This exam has no practical part."))
        self.assertEqual(self.stage("written"), "written")

    def test_cannot_advance_before_starting_or_after_the_attempt_ended(self):
        self.assertEqual(self.advance("both").status_code, 403)
        self.start("both")
        self.client.post("/api/events/", {"exam_id": "both", "event_type": "exam_quit", "client_id": str(uuid.uuid4())}, format="json")
        res = self.advance("both")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(self.stage("both"), "written")

    def test_other_batches_cannot_use_the_exam(self):
        Exam.objects.filter(pk=self.both.pk).update(batch=99)
        self.assertEqual(self.start("both").status_code, 403)

    def test_exam_finished_event_completes_the_attempt(self):
        self.start("both")
        self.advance("both")
        res = self.client.post("/api/events/", {"exam_id": "both", "event_type": "exam_finished", "client_id": str(uuid.uuid4())}, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(ExamAttempt.objects.get().status, "completed")
        self.assertEqual(self.start("both").status_code, 403)  # finished means finished

    def test_written_submitted_event_does_not_end_the_attempt(self):
        self.start("both")
        self.client.post("/api/events/", {"exam_id": "both", "event_type": "written_submitted", "client_id": str(uuid.uuid4())}, format="json")
        self.assertEqual(ExamAttempt.objects.get().status, "in_progress")

    def test_advance_query_count(self):
        self.start("both")
        with self.assertNumQueries(6):  # auth, exam, attempt, stage update, attempt.student, event insert
            self.advance("both")


class TeacherAdvanceTests(DashboardBase):
    def setUp(self):
        super().setUp()
        self.math.practical_enabled = True
        self.math.practical_instructions = "Do the lab"
        self.math.save()
        self.url = f"/teacher/exams/math-101/attempts/{self.ann_attempt.pk}/advance/"

    def test_teacher_moves_a_stuck_student_to_the_practical_part(self):
        res = self.as_user("mathteacher").post(self.url)
        self.assertEqual(res.json(), {"ok": True, "changed": 1})
        self.ann_attempt.refresh_from_db()
        self.assertEqual(self.ann_attempt.stage, "practical")
        self.assertEqual(ProctorEvent.objects.get(event_type="stage_advanced").detail, "written->practical by mathteacher")

    def test_second_click_changes_nothing(self):
        client = self.as_user("mathteacher")
        client.post(self.url)
        self.assertEqual(client.post(self.url).json()["changed"], 0)
        self.assertEqual(ProctorEvent.objects.filter(event_type="stage_advanced").count(), 1)

    def test_exams_without_a_practical_part_cannot_be_advanced(self):
        self.math.practical_enabled = False
        self.math.save()
        self.assertEqual(self.as_user("mathteacher").post(self.url).json()["changed"], 0)

    def test_other_subjects_teacher_gets_404_and_get_or_csrf_fail(self):
        self.assertEqual(self.as_user("physteacher").post(self.url).status_code, 404)
        self.assertEqual(self.as_user("mathteacher").get(self.url).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.login(username="mathteacher", password="pw")
        self.assertEqual(strict.post(self.url).status_code, 403)
        self.ann_attempt.refresh_from_db()
        self.assertEqual(self.ann_attempt.stage, "written")

    def test_live_rows_show_the_part_and_whether_advancing_is_possible(self):
        row = self.live(self.as_user("mathteacher"))[0]
        self.assertEqual((row["stage"], row["can_advance"]), ("written", True))
        services.advance_attempts(ExamAttempt.objects.filter(pk=self.ann_attempt.pk), "t")
        row = self.live(self.as_user("mathteacher"))[0]
        self.assertEqual((row["stage"], row["can_advance"]), ("practical", False))

    def test_timeline_labels_the_new_events(self):
        self.event(self.ann, self.math, "written_submitted")
        self.event(self.ann, self.math, "stage_advanced", "written->practical by t")
        self.event(self.ann, self.math, "exam_finished")
        html = self.as_user("mathteacher").get("/teacher/exams/math-101/students/1/").content.decode()
        for label in ("Submitted the written part", "Moved to the practical part", "Finished the exam"):
            self.assertIn(label, html)



class ModeMigrationTests(TransactionTestCase):
    """The old single `mode` becomes the two stage switches without losing anyone's setting."""

    def test_modes_are_carried_over_both_ways(self):
        executor = MigrationExecutor(connection)
        executor.migrate([("proctoring", "0009_examattempt_extra_minutes")])
        old = executor.loader.project_state([("proctoring", "0009_examattempt_extra_minutes")]).apps
        OldExam = old.get_model("proctoring", "Exam")
        OldExam.objects.create(exam_id="f", name="F", form_url="https://f", mode="form")
        OldExam.objects.create(exam_id="p", name="P", form_url="https://p", mode="practical")

        executor = MigrationExecutor(connection)
        executor.migrate([("proctoring", "0010_exam_stages")])
        # read through the schema as of 0010: later migrations add columns the current model already expects
        stage_state = executor.loader.project_state([("proctoring", "0010_exam_stages")]).apps
        exams = {e.exam_id: (e.written_enabled, e.practical_enabled) for e in stage_state.get_model("proctoring", "Exam").objects.all()}
        self.assertEqual(exams, {"f": (True, False), "p": (False, True)})

        executor = MigrationExecutor(connection)
        executor.migrate([("proctoring", "0009_examattempt_extra_minutes")])
        old = executor.loader.project_state([("proctoring", "0009_examattempt_extra_minutes")]).apps
        modes = dict(old.get_model("proctoring", "Exam").objects.values_list("exam_id", "mode"))
        self.assertEqual(modes, {"f": "form", "p": "practical"})
        MigrationExecutor(connection).migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())
