from django.core.management.base import BaseCommand

from apps.proctoring import services


class Command(BaseCommand):
    help = "Retention sweep: delete screenshots and webcam photos of exams that ended (or were archived) more than N days ago."

    def add_arguments(self, parser):
        parser.add_argument("--older-than-days", type=int, required=True)
        parser.add_argument("--dry-run", action="store_true", help="Only report what would be deleted")

    def handle(self, *args, older_than_days, dry_run, **options):
        results = services.purge_old_evidence(older_than_days, dry_run=dry_run)
        verb = "Would delete" if dry_run else "Deleted"
        for exam, count in results:
            self.stdout.write(f"{verb} {count} image(s) of {exam.exam_id}")
        if not results:
            self.stdout.write("Nothing to delete.")
