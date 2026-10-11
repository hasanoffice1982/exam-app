from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from apps.proctoring import marking
from apps.proctoring.models import ExamAttempt

from .test_dashboard import DashboardBase

HEADERS = "Timestamp,Email Address,Roll number,Score\n"


def csv_upload(body: str, name: str = "responses.csv") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, body.encode("utf-8-sig"), content_type="text/csv")


class ParsingTests(SimpleTestCase):
    def test_parse_score(self):
        self.assertEqual(marking.parse_score("8 / 10"), (8.0, 10.0))
        self.assertEqual(marking.parse_score("8.5/10"), (8.5, 10.0))
        self.assertEqual(marking.parse_score("7"), (7.0, None))
        for junk in ("", "n/a", "ten", None):
            self.assertEqual(marking.parse_score(junk), (None, None))

    def test_roll_normalisation_handles_spreadsheet_floats(self):
        self.assertEqual(marking.normalise_roll(" 81.0 "), "81")
        self.assertEqual(marking.normalise_roll("A-12"), "a-12")
        self.assertEqual(marking.normalise_roll("1.5"), "1.5")

    def test_column_guessing(self):
        headers = ["Timestamp", "Email Address", "Roll number", "Score", "Q1"]
        self.assertEqual(marking.guess_column(headers, marking.ROLL_HINTS), "Roll number")
        self.assertEqual(marking.guess_column(headers, marking.SCORE_HINTS), "Score")
        self.assertIsNone(marking.guess_column(["a", "b"], marking.ROLL_HINTS))

    def test_read_responses_handles_bom_and_trims(self):
        parsed = marking.read_responses(("﻿" + HEADERS + "t, a@x.com , 1 , 8 / 10\n").encode("utf-8"))
        self.assertEqual(parsed.headers, ["Timestamp", "Email Address", "Roll number", "Score"])
        self.assertEqual(parsed.rows[0]["Roll number"], "1")

    def test_read_responses_rejects_bad_input(self):
        with self.assertRaises(marking.MarkingError):
            marking.read_responses(b"\xff\xfe\x00bad")  # not UTF-8
        with self.assertRaises(marking.MarkingError):
            marking.read_responses(b"")
        with self.assertRaises(marking.MarkingError):
            marking.read_responses(b"x" * (marking.MAX_UPLOAD_BYTES + 1))
        many = HEADERS + "t,e,1,1\n" * (marking.MAX_ROWS + 1)
        with self.assertRaisesMessage(marking.MarkingError, "Too many rows"):
            marking.read_responses(many.encode())


def live(roll, status="in_progress", flag="clean", score=0, name="N"):
    return {"roll_number": roll, "name": name, "batch": 81, "status": status, "status_label": status, "flag": flag, "score": score}


class PolicyTests(SimpleTestCase):
    def build(self, live_rows, csv_text):
        return marking.build_marks(live_rows, marking.read_responses(csv_text.encode()))

    def test_form_score_becomes_the_mark(self):
        rows, outside, used = self.build([live("1")], HEADERS + "t,a@x.com,1,8 / 10\n")
        self.assertEqual((rows[0]["final_mark"], rows[0]["form_score"], rows[0]["form_max"]), (8, 8, 10))
        self.assertEqual(rows[0]["note"], "")
        self.assertEqual((outside, used), ([], {"roll": "Roll number", "score": "Score"}))

    def test_quit_is_zero_even_if_the_form_was_submitted(self):
        rows, _, _ = self.build([live("1", status=ExamAttempt.Status.QUIT)], HEADERS + "t,a,1,9 / 10\n")
        self.assertEqual(rows[0]["final_mark"], 0)
        self.assertIn("Quit the exam (marked 0)", rows[0]["note"])
        self.assertEqual(rows[0]["form_score"], 9)  # the raw score is still shown

    def test_force_ended_is_left_blank_for_the_teacher(self):
        rows, _, _ = self.build([live("1", status=ExamAttempt.Status.FORCE_ENDED)], HEADERS + "t,a,1,9 / 10\n")
        self.assertIsNone(rows[0]["final_mark"])
        self.assertIn("decide manually", rows[0]["note"])

    def test_missing_submission_is_blank_not_zero(self):
        rows, _, _ = self.build([live("1"), live("2")], HEADERS + "t,a,1,5 / 10\n")
        self.assertEqual(rows[1]["final_mark"], None)
        self.assertIn("No form submission", rows[1]["note"])

    def test_flagged_students_get_a_review_note_but_keep_their_score(self):
        rows, _, _ = self.build([live("1", flag="flagged", score=7)], HEADERS + "t,a,1,8 / 10\n")
        self.assertEqual(rows[0]["final_mark"], 8)
        self.assertIn("Flagged (proctor score 7)", rows[0]["note"])

    def test_latest_of_multiple_submissions_is_used(self):
        csv_text = HEADERS + "2026/01/01 09:00:00,a,1,3 / 10\n2026/01/01 10:00:00,a,1,9 / 10\n2026/01/01 08:00:00,a,1,1 / 10\n"
        rows, _, _ = self.build([live("1")], csv_text)
        self.assertEqual(rows[0]["final_mark"], 9)
        self.assertIn("3 submissions, latest used", rows[0]["note"])

    def test_submissions_without_an_attempt_are_reported(self):
        rows, outside, _ = self.build([live("1")], HEADERS + "t,a,1,8 / 10\nt,b,99,10 / 10\nt,c,,10 / 10\n")
        self.assertEqual(outside, [{"roll": "99", "score": "10 / 10", "submissions": 1}])  # blank roll ignored

    def test_float_rolls_from_sheets_still_match(self):
        rows, outside, _ = self.build([live("81")], HEADERS + "t,a,81.0,6 / 10\n")
        self.assertEqual(rows[0]["final_mark"], 6)
        self.assertEqual(outside, [])

    def test_missing_columns_explain_what_was_found(self):
        with self.assertRaisesMessage(marking.MarkingError, "Could not find the roll number column"):
            self.build([live("1")], "Name,Score\nx,1\n")
        with self.assertRaisesMessage(marking.MarkingError, "Columns in your file"):
            marking.build_marks([live("1")], marking.read_responses(b"Roll number,Q1\n1,x\n"))

    def test_explicit_columns_override_detection(self):
        responses = marking.read_responses(b"ID,Total\n1,5 / 10\n")
        rows, _, used = marking.build_marks([live("1")], responses, "ID", "Total")
        self.assertEqual((rows[0]["final_mark"], used), (5, {"roll": "ID", "score": "Total"}))


class MarksViewTests(DashboardBase):
    url = "/teacher/exams/math-101/marks/"

    def post(self, client, body, **extra):
        return client.post(self.url, {"responses": csv_upload(body), **extra})

    def test_access_is_scoped(self):
        self.assertEqual(Client_get(self.url).status_code, 302)
        self.assertEqual(self.as_user("physteacher").get(self.url).status_code, 404)
        self.assertEqual(self.as_user("physteacher").post(self.url, {"responses": csv_upload(HEADERS)}).status_code, 404)
        self.assertEqual(self.as_user("mathteacher").get(self.url).status_code, 200)

    def test_preview_shows_marks_and_outside_submissions(self):
        res = self.post(self.as_user("mathteacher"), HEADERS + "t,a,1,8 / 10\nt,z,77,10 / 10\n")
        self.assertContains(res, "Ann")
        self.assertContains(res, "<strong>8</strong>")
        self.assertContains(res, "Submitted outside the app")
        self.assertContains(res, "77")

    def test_quit_student_is_zero_in_the_view(self):
        ExamAttempt.objects.filter(pk=self.ann_attempt.pk).update(status="quit")
        res = self.post(self.as_user("mathteacher"), HEADERS + "t,a,1,8 / 10\n")
        self.assertContains(res, "Quit the exam (marked 0)")
        self.assertContains(res, "<strong>0</strong>")

    def test_download_csv(self):
        res = self.post(self.as_user("mathteacher"), HEADERS + "t,a,1,8 / 10\n", download="1")
        self.assertEqual(res["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("math-101-marks.csv", res["Content-Disposition"])
        lines = res.content.decode().strip().splitlines()
        self.assertEqual(lines[0], ",".join(marking.MARK_COLUMNS))
        self.assertTrue(lines[1].startswith("1,Ann,81,"))
        self.assertEqual(len(lines), 2)  # only this exam's students

    def test_download_neutralises_formula_injection(self):
        self.ann.name = "=1+1"
        self.ann.save()
        res = self.post(self.as_user("mathteacher"), HEADERS + "t,a,1,8 / 10\n", download="1")
        self.assertIn("'=1+1", res.content.decode())
        self.assertNotIn(",=1+1", res.content.decode())

    def test_bad_uploads_show_errors_instead_of_crashing(self):
        client = self.as_user("mathteacher")
        for upload, message in (
            (SimpleUploadedFile("x.txt", b"a,b"), "Please upload a .csv file"),
            (csv_upload("Name,Score\nx,1\n"), "Could not find the roll number column"),
            (SimpleUploadedFile("x.csv", b"\xff\xfe\x00"), "UTF-8"),
        ):
            res = client.post(self.url, {"responses": upload})
            self.assertEqual(res.status_code, 200)
            self.assertContains(res, message)
        self.assertEqual(client.post(self.url, {}).status_code, 200)  # no file at all

    def test_uploaded_html_in_cells_is_escaped(self):
        res = self.post(self.as_user("mathteacher"), HEADERS + "t,a,1,8 / 10\nt,a,<script>alert(1)</script>,1\n")
        self.assertNotContains(res, "<script>alert(1)</script>")
        self.assertContains(res, "&lt;script&gt;")

    def test_nothing_is_stored(self):
        from apps.proctoring.models import ProctorEvent

        before = ProctorEvent.objects.count()
        self.post(self.as_user("mathteacher"), HEADERS + "t,a,1,8 / 10\n")
        self.assertEqual(ProctorEvent.objects.count(), before)


def Client_get(url):
    from django.test import Client

    return Client().get(url)
