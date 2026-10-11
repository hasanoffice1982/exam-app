from django.contrib.auth.models import Group, Permission

TEACHER_GROUP = "Teachers"

# view everything about their exams; change only what teachers may edit (exam settings, attempts)
TEACHER_PERMISSIONS = [
    "view_exam",
    "change_exam",
    "view_examattempt",
    "change_examattempt",
    "view_proctorevent",
    "view_proctorscreenshot",
    "view_consent",
]


def ensure_teacher_group() -> Group:
    group, _ = Group.objects.get_or_create(name=TEACHER_GROUP)
    group.permissions.set(Permission.objects.filter(content_type__app_label="proctoring", codename__in=TEACHER_PERMISSIONS))
    return group
