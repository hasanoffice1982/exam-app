"""How suspicious is an event? Weights are deliberately simple so teachers can reason about them."""
from .event_types import EventType as E

EVENT_LABELS = {
    E.TAB_SWITCH: "Switched away from exam",
    E.RETURNED_TO_EXAM: "Returned to exam",
    E.EXITED_FULLSCREEN: "Left full screen",
    E.CLIPBOARD_ATTEMPT: "Tried to copy/paste",
    E.DEVTOOLS_ATTEMPT: "Tried to open developer tools",
    E.BLOCKED_SHORTCUT: "Blocked shortcut (print/save/source)",
    E.BLOCKED_NAVIGATION: "Tried to leave the exam page",
    E.DISPLAY_ADDED: "Extra display connected",
    E.BLOCKED_APP_DETECTED: "Screen-share/remote/recording app",
    E.WATCH_APP_DETECTED: "Chat/meeting app running",
    E.CAMERA_UNAVAILABLE: "Camera unavailable or covered",
    E.CONNECTION_LOST: "Connection lost",
    E.CONNECTION_RESTORED: "Connection restored",
    E.WRITTEN_SUBMITTED: "Submitted the written part",
    E.EXAM_FINISHED: "Finished the exam",
    E.EXAM_QUIT: "Quit the exam",
    E.TIME_UP: "Time ran out",
    E.FORCE_ENDED: "Ended by teacher",
    E.EXAM_RESUMED: "Reopened the exam (restart)",
    E.STAGE_ADVANCED: "Moved to the practical part",
    E.TIME_EXTENDED: "Teacher gave extra time",
}

WEIGHTS = {
    E.TAB_SWITCH: 1,
    E.EXITED_FULLSCREEN: 2,
    E.CLIPBOARD_ATTEMPT: 1,
    E.DEVTOOLS_ATTEMPT: 2,
    E.BLOCKED_SHORTCUT: 1,
    E.BLOCKED_NAVIGATION: 1,
    E.DISPLAY_ADDED: 3,
    E.BLOCKED_APP_DETECTED: 3,
    E.WATCH_APP_DETECTED: 1,
    E.CAMERA_UNAVAILABLE: 2,
}

REVIEW_AT = 1
FLAGGED_AT = 5


def label(event_type: str) -> str:
    return EVENT_LABELS.get(event_type, event_type)  # unknown/new types still display


def weight(event_type: str) -> int:
    return WEIGHTS.get(event_type, 0)


def score(counts: dict[str, int]) -> int:
    return sum(weight(event_type) * n for event_type, n in counts.items())


def flag_for(total: int) -> str:
    if total >= FLAGGED_AT:
        return "flagged"
    return "review" if total >= REVIEW_AT else "clean"


def summarize(counts: dict[str, int]) -> tuple[int, str]:
    """(score, flag) for a student's event counts: the one place both dashboards get these."""
    total = score(counts)
    return total, flag_for(total)
