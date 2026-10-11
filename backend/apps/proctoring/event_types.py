"""Single list of event names. The desktop client mirrors it in desktop/src/main/eventTypes.ts
(a desktop test fails if the two drift apart)."""
from enum import StrEnum


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
    CONNECTION_LOST = "connection_lost"
    CONNECTION_RESTORED = "connection_restored"
    EXAM_QUIT = "exam_quit"
    TIME_UP = "time_up"
    # written by the server, never sent by clients:
    FORCE_ENDED = "force_ended"
    EXAM_RESUMED = "exam_resumed"
    TIME_EXTENDED = "time_extended"
