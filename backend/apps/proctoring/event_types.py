"""Single list of event names. The desktop client mirrors it in desktop/src/main/eventTypes.ts
(a desktop test fails if the two drift apart)."""
try:
    from enum import StrEnum
except ImportError:  # Python < 3.11 (e.g. PythonAnywhere's 3.10)
    from enum import Enum

    class StrEnum(str, Enum):
        def __str__(self) -> str:
            return str(self.value)


class EventType(StrEnum):
    TAB_SWITCH = "tab_switch"
    RETURNED_TO_EXAM = "returned_to_exam"
    EXITED_FULLSCREEN = "exited_fullscreen"
    CLIPBOARD_ATTEMPT = "clipboard_attempt"
    DEVTOOLS_ATTEMPT = "devtools_attempt"
    BLOCKED_SHORTCUT = "blocked_shortcut"
    BLOCKED_NAVIGATION = "blocked_navigation"
    DISPLAY_ADDED = "display_added"
    BLOCKED_APP_DETECTED = "blocked_app_detected"
    WATCH_APP_DETECTED = "watch_app_detected"
    CAMERA_UNAVAILABLE = "camera_unavailable"
    SCREENSHOT_FAILED = "screenshot_failed"
    CONNECTION_LOST = "connection_lost"
    CONNECTION_RESTORED = "connection_restored"
    WRITTEN_SUBMITTED = "written_submitted"
    EXAM_FINISHED = "exam_finished"
    EXAM_QUIT = "exam_quit"
    TIME_UP = "time_up"
    # written by the server, never sent by clients:
    FORCE_ENDED = "force_ended"
    EXAM_RESUMED = "exam_resumed"
    STAGE_ADVANCED = "stage_advanced"
    TIME_EXTENDED = "time_extended"


# Written by the server on teacher/student actions; a client must never be able to claim them.
SERVER_ONLY = frozenset({EventType.FORCE_ENDED, EventType.EXAM_RESUMED, EventType.STAGE_ADVANCED, EventType.TIME_EXTENDED})
CLIENT_SENDABLE = tuple(e.value for e in EventType if e not in SERVER_ONLY)
