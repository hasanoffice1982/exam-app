from django.core.management.base import BaseCommand

from apps.proctoring.models import Exam

SAMPLES = [
    {
        "exam_id": "math-101",
        "name": "Mathematics 101",
        "form_url": "https://docs.google.com/forms/d/e/REPLACE_WITH_REAL_FORM_ID/viewform?embedded=true",
        "batch": 81,
    },
    {
        "exam_id": "physics-101",
        "name": "Physics 101",
        "form_url": "https://docs.google.com/forms/d/e/REPLACE_WITH_REAL_FORM_ID/viewform",
        "batch": 81,
    },
]


class Command(BaseCommand):
    help = "Create sample Exam rows (idempotent)."

    def handle(self, *args, **options):
        for data in SAMPLES:
            exam_id = data["exam_id"]
            _, created = Exam.objects.get_or_create(
                exam_id=exam_id, defaults={k: v for k, v in data.items() if k != "exam_id"}
            )
            self.stdout.write(f"{'Created' if created else 'Exists '} {exam_id}")

        from apps.proctoring.models import Student

        demo, created = Student.objects.get_or_create(roll_number="42", defaults={"name": "Test User", "email": "student@example.com", "batch": 81})
        if created:
            demo.set_password("demo1234")  # dev-only demo account
            demo.save()
            self.stdout.write("Created demo student (roll 42)")
