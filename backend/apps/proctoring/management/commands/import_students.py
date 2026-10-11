import csv

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.proctoring.models import Student


class Command(BaseCommand):
    help = "Import/update students from a CSV with header: roll_number,name,email[,batch]"

    def add_arguments(self, parser):
        parser.add_argument("csv_path")

    def handle(self, *args, csv_path, **options):
        try:
            f = open(csv_path, newline="", encoding="utf-8-sig")
        except OSError as e:
            raise CommandError(str(e))
        with f:
            for line, row in enumerate(csv.DictReader(f), start=2):
                roll = row["roll_number"].strip()
                batch_text = (row.get("batch") or "").strip()
                student = Student.objects.filter(roll_number=roll).first() or Student(roll_number=roll)
                created = student._state.adding
                student.name = row["name"].strip()
                student.email = row["email"].strip()
                if batch_text:
                    student.batch = int(batch_text)
                student._changed_by = "csv import"
                try:
                    student.save()
                except ValidationError as e:
                    self.stderr.write(f"line {line}: SKIPPED {roll}: {'; '.join(e.messages)}")
                    continue
                self.stdout.write(f"{'Created' if created else 'Updated'} {student}")
