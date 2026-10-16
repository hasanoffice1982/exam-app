from django.test import TestCase

from apps.proctoring.models import Subject

from .helpers import authed_client, make_exam, make_student


class SubjectVisibilityTests(TestCase):
    def setUp(self):
        self.math = Subject.objects.create(name="Mathematics")
        self.physics = Subject.objects.create(name="Physics")
        self.ann = make_student("1", "Ann")
        self.bob = make_student("2", "Bob", email="bob@example.com")
        self.ann.subjects.add(self.math)
        self.bob.subjects.add(self.physics)
        make_exam("math-101", subject=self.math)
        make_exam("physics-101", subject=self.physics)
        make_exam("general-101")  # no subject: the whole batch

    def exam_ids(self, student):
        client, _ = authed_client(student)
        return {e["exam_id"] for e in client.get("/api/exams/").json()}

    def test_student_sees_only_own_subjects_and_subjectless_exams(self):
        self.assertEqual(self.exam_ids(self.ann), {"math-101", "general-101"})
        self.assertEqual(self.exam_ids(self.bob), {"physics-101", "general-101"})

    def test_student_without_subjects_sees_only_subjectless_exams(self):
        self.assertEqual(self.exam_ids(make_student("3", "Cy", email="c@example.com")), {"general-101"})

    def test_other_batch_never_sees_it_even_with_the_subject(self):
        dan = make_student("4", "Dan", email="d@example.com", batch=82)
        dan.subjects.add(self.math)
        self.assertEqual(self.exam_ids(dan), set())

    def test_config_of_another_subjects_exam_is_refused(self):
        client, _ = authed_client(self.ann)
        self.assertEqual(client.get("/api/config/physics-101/").status_code, 403)
        self.assertEqual(client.get("/api/config/math-101/").status_code, 200)

    def test_exam_roster_is_narrowed_to_the_subject(self):
        math = make_exam("math-102", subject=self.math)
        self.assertEqual(list(math.students()), [self.ann])
        everyone = make_exam("all-101")
        self.assertEqual(set(everyone.students()), {self.ann, self.bob})
