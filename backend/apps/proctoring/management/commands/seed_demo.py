"""Fills a database with realistic demo data (students, exams, attempts, events, screenshots) for demos and manuals.

Use a throwaway database, never your real one:
    DATABASE_PATH=/tmp/demo/db.sqlite3 MEDIA_ROOT=/tmp/demo/media python manage.py migrate
    DATABASE_PATH=... MEDIA_ROOT=... python manage.py seed_demo --sample-images manuals/src/sample
"""
import random
import shutil
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.proctoring import services
from apps.proctoring.models import (
    AuditEntry, Exam, ExamAttempt, ProctorEvent, ProctorScreenshot, Student, StudentToken,
)
from apps.proctoring.teachers import ensure_teacher_group

DEMO_PASSWORD = "Demo-pass-1"
ADMIN = ("admin", "Admin-demo-1")
TEACHERS = [("rahman", "Rahman-demo-1", "Dr. Rahman"), ("sultana", "Sultana-demo-1", "Ms. Sultana")]
FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSdemoDEMOdemo/viewform"

# (roll, name, activated)
BATCH_81 = [
    ("81001", "Ayesha Rahman", True), ("81002", "Tanvir Hasan", True), ("81003", "Nusrat Jahan", True),
    ("81004", "Rafiq Ahmed", True), ("81005", "Sadia Islam", True), ("81006", "Imran Khan", True),
    ("81007", "Mahmud Hasan", True), ("81008", "Farhana Akter", True), ("81009", "Karim Uddin", True),
    ("81010", "Shirin Sultana", False), ("81011", "Jamal Hossain", False), ("81012", "Rina Das", False),
]
BATCH_82 = [("82001", "Tasnim Chowdhury", True), ("82002", "Habib Rahman", True), ("82003", "Mitu Barua", False)]


class Command(BaseCommand):
    help = "Create demo users, students, exams and activity (idempotent: wipes and rebuilds the demo content)."

    def add_arguments(self, parser):
        parser.add_argument("--sample-images", help="Folder with screen-1.png... and webcam-1.jpg... to attach as evidence")
        parser.add_argument("--form-url", default=FORM_URL, help="Link the demo exams load as their written paper")
        parser.add_argument("--force", action="store_true", help="Skip the 'database name must contain demo' safety check (tests only)")

    def handle(self, *args, sample_images=None, force=False, form_url=FORM_URL, **options):
        if "demo" not in str(settings.DATABASES["default"]["NAME"]).lower() and not force:
            raise CommandError("Refusing to seed: DATABASE_PATH must contain 'demo' so a real database is never filled with fake data.")
        self.images = Path(sample_images) if sample_images else None
        self.form_url = form_url
        self.rng = random.Random(7)
        self.now = timezone.now()
        self.wipe()
        self.create_users()
        students = self.create_students()
        self.create_exams(students)
        self.stdout.write(self.style.SUCCESS(
            f"Demo ready: admin '{ADMIN[0]}' / '{ADMIN[1]}', teachers {[t[0] for t in TEACHERS]}, student password '{DEMO_PASSWORD}'."
        ))

    # ---- helpers ---------------------------------------------------------------------------------

    def wipe(self):
        for model in (ProctorScreenshot, ProctorEvent, ExamAttempt, StudentToken, AuditEntry, Exam, Student):
            model.objects.all().delete()
        get_user_model().objects.filter(username__in=[ADMIN[0], *[t[0] for t in TEACHERS]]).delete()
        shutil.rmtree(Path(settings.MEDIA_ROOT) / "screenshots", ignore_errors=True)

    def create_users(self):
        User = get_user_model()
        User.objects.create_superuser(ADMIN[0], "admin@example.com", ADMIN[1])
        group = ensure_teacher_group()
        self.teachers = {}
        for username, password, display in TEACHERS:
            first, _, last = display.partition(" ")
            user = User.objects.create_user(username, f"{username}@example.com", password, first_name=display.split()[0], last_name=last, is_staff=False)
            user.groups.add(group)
            self.teachers[username] = user

    def create_students(self):
        out = {}
        for batch, rows in ((81, BATCH_81), (82, BATCH_82)):
            for roll, name, activated in rows:
                s = Student(roll_number=roll, name=name, email=f"{roll}@school.example", batch=batch)
                if activated:
                    s.set_password(DEMO_PASSWORD)
                s.save()
                out[roll] = s
        return out

    def exam(self, exam_id, name, **kwargs):
        defaults = {"form_url": self.form_url, "monitoring_enabled": True}
        defaults.update(kwargs)
        exam = Exam(exam_id=exam_id, name=name, **defaults)
        exam.full_clean()
        exam.save()
        return exam

    def at(self, minutes_ago):
        return self.now - timedelta(minutes=minutes_ago)

    def event(self, student, exam, event_type, minutes_ago, detail=""):
        return ProctorEvent.objects.create(student=student.label, exam=exam, event_type=event_type, detail=detail, timestamp=self.at(minutes_ago))

    def shot(self, student, exam, minutes_ago, kind, index):
        shot = ProctorScreenshot(student=student.label, exam=exam, kind=kind, timestamp=self.at(minutes_ago))
        data, ext = self.image_bytes(kind, index)
        shot.file.save(f"demo-{student.roll_number}-{kind}-{index}.{ext}", ContentFile(data), save=False)
        shot.save()

    def image_bytes(self, kind, index):
        prefix, ext = ("screen", "png") if kind == "screen" else ("webcam", "jpg")
        if self.images:
            files = sorted(self.images.glob(f"{prefix}-*.{ext}"))
            if files:
                return files[index % len(files)].read_bytes(), ext
        # a valid 1x1 image so the upload rules (and viewers) are happy when no samples are given
        png = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc0000003010100c9fe92ef0000000049454e44ae426082")
        return (png, "png") if ext == "png" else (b"\xff\xd8\xff\xe0" + b"\x00" * 16, "jpg")

    def attempt(self, student, exam, status="in_progress", stage="written", started=35, ended=None, seen=0, extra=0, token=True):
        attempt = ExamAttempt.objects.create(
            student=student, exam=exam, status=status, stage=stage, started_at=self.at(started),
            ended_at=self.at(ended) if ended is not None else None, extra_minutes=extra,
        )
        if token and status == "in_progress":
            StudentToken.objects.create(
                student=student, key_hash=f"demo-{student.roll_number}", expires_at=self.now + timedelta(hours=6),
                last_seen_at=self.at(seen) if seen is not None else None,
            )
        return attempt

    # ---- the demo exams ----------------------------------------------------------------------------

    def create_exams(self, st):
        physics = self.exam(
            "physics-mid", "Physics Midterm", batch=81, written_enabled=True, practical_enabled=True,
            practical_instructions="Using the simulator, build the circuit described in Question 4 of the written paper.\nSave your file as <roll>-circuit and upload it to the class drive.\nWhen you are finished, click Finish practical.",
            practical_url="https://example.com/lab-sheet", practical_screenshot_seconds=60, webcam_enabled=True, webcam_interval_seconds=180,
            starts_at=self.at(40), ends_at=self.now + timedelta(minutes=80),
        )
        physics.teachers.add(self.teachers["rahman"])
        maths = self.exam("math-quiz", "Mathematics Quiz 1", batch=81, starts_at=self.at(60 * 26), ends_at=self.at(60 * 25))
        maths.teachers.add(self.teachers["rahman"], self.teachers["sultana"])
        chem = self.exam(
            "chem-lab", "Chemistry Lab Practical", batch=82, written_enabled=False, practical_enabled=True,
            practical_instructions="Perform the titration shown in the lab sheet and record your readings in the spreadsheet.",
            starts_at=self.now + timedelta(days=1), ends_at=self.now + timedelta(days=1, hours=2),
        )
        chem.teachers.add(self.teachers["sultana"])
        bio = self.exam("bio-final", "Biology Final (2025)", batch=81, starts_at=self.at(60 * 24 * 40), ends_at=self.at(60 * 24 * 40 - 120),
                        archived=True, archived_at=self.at(60 * 24 * 30))
        bio.teachers.add(self.teachers["rahman"])
        AuditEntry.objects.create(exam=bio, exam_label=f"{bio.name} ({bio.exam_id})", action="archived", performed_by="rahman", at=self.at(60 * 24 * 30))
        AuditEntry.objects.create(exam=bio, exam_label=f"{bio.name} ({bio.exam_id})", action="evidence deleted", detail="212 image(s), 18340 KB; retention 90 days", performed_by="admin", at=self.at(60 * 24 * 3))

        # Physics: one student per interesting situation
        s = st
        a = self.attempt(s["81001"], physics, stage="practical", started=38, seen=0)
        for m, t in ((30, "tab_switch"), (29, "returned_to_exam"), (24, "stage_advanced")):
            self.event(s["81001"], physics, t, m, "written->practical by student" if t == "stage_advanced" else "")
        self.event(s["81001"], physics, "written_submitted", 25)
        for i, m in enumerate((36, 20, 12)):
            self.shot(s["81001"], physics, m, "webcam", i)
        for i, m in enumerate((22, 16, 10, 4)):
            self.shot(s["81001"], physics, m, "screen", i % 2)

        self.attempt(s["81002"], physics, started=37, seen=0)
        for m, t, d in ((31, "tab_switch", ""), (30, "returned_to_exam", ""), (27, "clipboard_attempt", "v"), (22, "tab_switch", ""),
                        (21, "returned_to_exam", ""), (17, "devtools_attempt", "F12"), (13, "tab_switch", ""), (12, "returned_to_exam", ""),
                        (8, "tab_switch", ""), (7, "returned_to_exam", ""), (3, "tab_switch", ""), (2, "returned_to_exam", "")):
            self.event(s["81002"], physics, t, m, d)
        for i, m in enumerate((22, 13, 8, 3)):
            self.shot(s["81002"], physics, m, "screen", 2 + (i % 2))
        self.shot(s["81002"], physics, 35, "webcam", 1)

        self.attempt(s["81003"], physics, started=36, seen=0)
        self.event(s["81003"], physics, "returned_to_exam", 20)
        self.shot(s["81003"], physics, 34, "webcam", 2)

        self.attempt(s["81004"], physics, started=39, seen=9)
        self.event(s["81004"], physics, "connection_lost", 9)
        self.event(s["81004"], physics, "exam_resumed", 5)

        self.attempt(s["81005"], physics, status="completed", stage="practical", started=39, ended=6, token=False)
        self.event(s["81005"], physics, "written_submitted", 28)
        self.event(s["81005"], physics, "exam_finished", 6)

        self.attempt(s["81006"], physics, status="quit", started=38, ended=18, token=False)
        self.event(s["81006"], physics, "tab_switch", 19)
        self.event(s["81006"], physics, "exam_quit", 18)

        self.attempt(s["81007"], physics, status="force_ended", started=38, ended=14, token=False)
        for m in (20, 18):
            self.event(s["81007"], physics, "tab_switch", m)
        self.event(s["81007"], physics, "blocked_app_detected", 16, "TeamViewer")
        self.event(s["81007"], physics, "force_ended", 14, "rahman")

        self.attempt(s["81008"], physics, stage="practical", started=38, seen=1, extra=10)
        self.event(s["81008"], physics, "display_added", 15, "2 displays")
        self.event(s["81008"], physics, "blocked_app_detected", 11, "OBS Studio")
        self.event(s["81008"], physics, "time_extended", 5, "+10 min by rahman")
        for i, m in enumerate((14, 9, 4)):
            self.shot(s["81008"], physics, m, "screen", i % 2)
        self.shot(s["81008"], physics, 30, "webcam", 0)

        # Mathematics Quiz (finished yesterday): everyone completed
        for roll, name, _ in BATCH_81[:9]:
            self.attempt(s[roll], maths, status="completed", started=60 * 26, ended=60 * 26 - 30, token=False)
            self.event(s[roll], maths, "written_submitted", 60 * 26 - 25)
            self.event(s[roll], maths, "exam_finished", 60 * 26 - 30)
        self.event(s["81002"], maths, "tab_switch", 60 * 26 - 10)
        self.event(s["81002"], maths, "clipboard_attempt", 60 * 26 - 9, "c")
