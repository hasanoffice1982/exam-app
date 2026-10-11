/** Event names the client sends. Mirrors backend/apps/proctoring/event_types.py (a test checks they match). */
export const EventType = {
  TabSwitch: "tab_switch",
  ReturnedToExam: "returned_to_exam",
  ExitedFullscreen: "exited_fullscreen",
  ClipboardAttempt: "clipboard_attempt",
  DevtoolsAttempt: "devtools_attempt",
  BlockedShortcut: "blocked_shortcut",
  BlockedNavigation: "blocked_navigation",
  DisplayAdded: "display_added",
  BlockedAppDetected: "blocked_app_detected",
  WatchAppDetected: "watch_app_detected",
  CameraUnavailable: "camera_unavailable",
  ScreenshotFailed: "screenshot_failed",
  ConnectionLost: "connection_lost",
  ConnectionRestored: "connection_restored",
  WrittenSubmitted: "written_submitted",
  ExamFinished: "exam_finished",
  ExamQuit: "exam_quit",
  TimeUp: "time_up",
} as const;

export type EventTypeValue = (typeof EventType)[keyof typeof EventType];
