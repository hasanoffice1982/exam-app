from django.core.management.base import BaseCommand

from apps.proctoring import services
from apps.proctoring.models import Student


class Command(BaseCommand):
    help = "Deactivate every student of a batch (no more logins, sessions ended). Records are kept; reactivate in /admin/."

    def add_arguments(self, parser):
        parser.add_argument("batch", type=int)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, batch, dry_run, **options):
        students = Student.objects.filter(batch=batch, is_active=True)
        if dry_run:
            self.stdout.write(f"Would deactivate {students.count()} student(s) of batch {batch}")
            return
        count = services.deactivate_students(students, "deactivate_batch")
        self.stdout.write(f"Deactivated {count} student(s) of batch {batch}")
