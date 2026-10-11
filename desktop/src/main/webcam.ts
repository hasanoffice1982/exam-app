import { BrowserWindow, nativeImage, session, systemPreferences } from "electron";
import * as path from "path";

import { averageBrightness, dataUrlToBuffer, friendlyCameraError, isTooDark, withTimeout } from "./webcamUtils";

const CAMERA_PARTITION = "camera";
const CAPTURE_TIMEOUT_MS = 15_000;

/** Only the hidden camera window may use the camera; web pages (the exam form) get no permissions. */
export function configureSessions(): void {
  const web = session.defaultSession;
  web.setPermissionRequestHandler((_wc, _permission, callback) => callback(false));
  web.setPermissionCheckHandler(() => false);

  const cam = session.fromPartition(CAMERA_PARTITION);
  cam.setPermissionRequestHandler((wc, permission, callback) =>
    callback(permission === "media" && wc.getURL().startsWith("file://")),
  );
  cam.setPermissionCheckHandler((_wc, permission) => permission === "media");
}

/** macOS asks once per app; other platforms prompt on first use. Throws a student-readable reason. */
export async function requestCameraAccess(): Promise<void> {
  if (process.platform !== "darwin") return;
  const status = systemPreferences.getMediaAccessStatus("camera");
  if (status === "granted") return;
  if (status === "not-determined" && (await systemPreferences.askForMediaAccess("camera"))) return;
  throw new Error("Camera access is blocked. Allow it in System Settings > Privacy & Security > Camera, then restart the app");
}

export class WebcamCapturer {
  private win: BrowserWindow | null = null;

  /** Takes one JPEG. Rejects with a short reason if the camera is missing, busy, denied or covered. */
  async capture(): Promise<Buffer> {
    try {
      const win = await this.window();
      const dataUrl = (await withTimeout(
        win.webContents.executeJavaScript("window.capture()") as Promise<string>,
        CAPTURE_TIMEOUT_MS,
        "Camera did not respond",
      ));
      const jpeg = dataUrlToBuffer(dataUrl);
      const sample = nativeImage.createFromBuffer(jpeg).resize({ width: 16, height: 12 }).toBitmap();
      if (isTooDark(averageBrightness(sample))) throw new Error("Camera image is black (covered)");
      return jpeg;
    } catch (err) {
      this.dispose(); // a hung camera page must not block the next attempt
      throw new Error(friendlyCameraError(err instanceof Error ? err.message : String(err)));
    }
  }

  dispose(): void {
    if (this.win && !this.win.isDestroyed()) this.win.destroy();
    this.win = null;
  }

  private async window(): Promise<BrowserWindow> {
    if (this.win && !this.win.isDestroyed()) return this.win;
    const win = new BrowserWindow({
      show: false,
      width: 640,
      height: 480,
      webPreferences: {
        partition: CAMERA_PARTITION,
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
        devTools: false,
        backgroundThrottling: false,
      },
    });
    await win.loadFile(path.join(__dirname, "..", "camera", "camera.html"));
    this.win = win;
    return win;
  }
}
