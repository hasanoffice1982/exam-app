import { BrowserWindow, desktopCapturer, screen, systemPreferences } from "electron";

import { SCREENSHOT_JPEG_QUALITY, SCREENSHOT_MAX_WIDTH } from "./config";
import { fitWithin } from "./imageSize";
import { withTimeout } from "./webcamUtils";

/** Captures the display the window is on as a downscaled JPEG (small enough to upload quickly and store cheaply). */
export async function captureScreen(win: BrowserWindow): Promise<Buffer> {
  if (process.platform === "darwin") {
    const status = systemPreferences.getMediaAccessStatus("screen");
    if (status !== "granted") {
      throw new Error(
        `macOS Screen Recording permission is "${status}" - allow it in System Settings > Privacy & Security, then restart the app`,
      );
    }
  }
  const display = screen.getDisplayMatching(win.getBounds());
  // Ask the OS for the reduced size directly: cheaper than capturing at full resolution and resizing.
  const size = fitWithin(display.size.width, display.size.height, SCREENSHOT_MAX_WIDTH);
  const sources = await withTimeout(
    desktopCapturer.getSources({ types: ["screen"], thumbnailSize: size }),
    10_000,
    "Screen capture did not respond",
  );
  const source = sources.find((s) => s.display_id === String(display.id)) ?? sources[0];
  if (!source) throw new Error("No screen source available (check screen-recording permission)");

  const jpeg = source.thumbnail.toJPEG(SCREENSHOT_JPEG_QUALITY);
  if (jpeg.length === 0) throw new Error("Captured an empty image (screen-recording permission?)");
  return jpeg;
}
