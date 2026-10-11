from django.contrib.auth.models import Group

TEACHER_GROUP = "Teachers"


def ensure_teacher_group() -> Group:
    group, _ = Group.objects.get_or_create(name=TEACHER_GROUP)
    return group


def is_teacher(user) -> bool:
    """Who may use the teacher dashboard: teachers (their own exams only) and administrators (all exams)."""
    return bool(user.is_authenticated and (user.is_superuser or user.groups.filter(name=TEACHER_GROUP).exists()))
