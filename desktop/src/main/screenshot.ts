import { BrowserWindow, desktopCapturer, screen, systemPreferences } from "electron";

import { SCREENSHOT_JPEG_QUALITY, SCREENSHOT_MAX_WIDTH } from "./config";
import { fitWithin } from "./imageSize";
import { withTimeout } from "./webcamUtils";

/** Captures the display the window is on as a downscaled JPEG (small enough to upload quickly and store cheaply). */
export async function captureScreen(win: BrowserWindow, display: "window" | "cursor" = "window"): Promise<Buffer> {
  if (process.platform === "darwin") {
    const status = systemPreferences.getMediaAccessStatus("screen");
    if (status !== "granted") {
      throw new Error(
        `macOS Screen Recording permission is "${status}" - allow it in System Settings > Privacy & Security, then restart the app`,
      );
    }
  }
  // Written part: the display the exam window is on. Practical part: wherever the student is working.
  const target = display === "cursor" ? screen.getDisplayNearestPoint(screen.getCursorScreenPoint()) : screen.getDisplayMatching(win.getBounds());
  // Ask the OS for the reduced size directly: cheaper than capturing at full resolution and resizing.
  const size = fitWithin(target.size.width, target.size.height, SCREENSHOT_MAX_WIDTH);
  const sources = await withTimeout(
    desktopCapturer.getSources({ types: ["screen"], thumbnailSize: size }),
    10_000,
    "Screen capture did not respond",
  );
  const source = sources.find((s) => s.display_id === String(target.id)) ?? sources[0];
  if (!source) throw new Error("No screen source available (check screen-recording permission)");

  const jpeg = source.thumbnail.toJPEG(SCREENSHOT_JPEG_QUALITY);
  if (jpeg.length === 0) throw new Error("Captured an empty image (screen-recording permission?)");
  return jpeg;
}

/**
 * macOS only: make sure Screen Recording is allowed before an exam starts. The first capture attempt triggers the
 * system prompt (it gives up after 10 s if nobody answers). Throws a message the student can act on.
 */
export async function ensureScreenPermission(): Promise<void> {
  if (process.platform !== "darwin" || systemPreferences.getMediaAccessStatus("screen") === "granted") return;
  try {
    await withTimeout(desktopCapturer.getSources({ types: ["screen"], thumbnailSize: { width: 1, height: 1 } }), 10_000, "no answer");
  } catch {
    /* the prompt may be unanswered or denied: the status check below decides */
  }
  if (systemPreferences.getMediaAccessStatus("screen") !== "granted") {
    throw new Error(
      "Screen Recording permission is needed for this exam. Open System Settings > Privacy & Security > Screen & System Audio Recording, turn on ExamProctor, then quit and reopen the app",
    );
  }
}
