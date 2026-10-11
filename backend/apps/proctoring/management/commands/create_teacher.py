import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.proctoring.models import Exam
from apps.proctoring.teachers import ensure_teacher_group


class Command(BaseCommand):
    help = "Create (or update) a subject teacher who can only see and manage the given exams in /admin/."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--exams", required=True, help="Comma-separated exam_ids, e.g. math-101,physics-101")
        parser.add_argument("--email", default="")
        parser.add_argument("--password", help="Optional; a random one is generated and printed once if omitted")

    def handle(self, *args, username, exams, email, password, **options):
        slugs = [s.strip() for s in exams.split(",") if s.strip()]
        found = list(Exam.objects.filter(exam_id__in=slugs))
        missing = set(slugs) - {e.exam_id for e in found}
        if missing:
            raise CommandError(f"Unknown exam_id(s): {', '.join(sorted(missing))}")

        User = get_user_model()
        user, created = User.objects.get_or_create(username=username, defaults={"email": email, "is_staff": True})
        user.is_staff = True
        user.is_superuser = False
        if email:
            user.email = email
        if created or password:
            password = password or secrets.token_urlsafe(9)
            user.set_password(password)
            self.stdout.write(f"Password for {username}: {password}")
        user.save()
        user.groups.add(ensure_teacher_group())
        for exam in found:
            exam.teachers.add(user)
        self.stdout.write(f"{'Created' if created else 'Updated'} teacher {username} for {', '.join(slugs)}")
