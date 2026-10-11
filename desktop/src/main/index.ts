import { app, BrowserWindow, ipcMain, Menu, screen } from "electron";
import * as path from "path";

import { api, setToken } from "./api";
import { ExamMonitor } from "./monitor";
import { scanProcesses } from "./processes";
import { UploadQueue } from "./queue";
import { createSender } from "./sync";
import { configureSessions, requestCameraAccess, WebcamCapturer } from "./webcam";

let launcherWindow: BrowserWindow | null = null;
let consentTimestamp: string | null = null;
let session: StudentProfile | null = null;

const secureWebPreferences = {
  contextIsolation: true,
  nodeIntegration: false,
  sandbox: true,
} as const;

function createLauncherWindow(): void {
  launcherWindow = new BrowserWindow({
    width: 560,
    height: 700,
    resizable: true,
    webPreferences: { ...secureWebPreferences, preload: path.join(__dirname, "..", "preload", "index.js") },
  });
  launcherWindow.removeMenu();
  launcherWindow.setContentProtection(true); // the one-time password must not end up in screenshots or shared screens
  void launcherWindow.loadFile(path.join(__dirname, "..", "renderer", "index.html"));

  launcherWindow.on("closed", () => (launcherWindow = null));
}

function createExamWindow(config: ExamConfig): BrowserWindow {
  // Loads remote content: deliberately no preload and no Node access.
  const win = new BrowserWindow({
    width: 1280,
    height: 900,
    resizable: true,
    fullscreen: true,
    webPreferences: { ...secureWebPreferences, devTools: false },
  });
  win.removeMenu();
  // No Edit menu (Copy/Paste) during the exam. On macOS only Quit remains, which goes through the quit dialog.
  Menu.setApplicationMenu(process.platform === "darwin" ? Menu.buildFromTemplate([{ label: "ExamProctor", submenu: [{ role: "quit" }] }]) : null);
  void win.loadURL(config.form_url);
  return win;
}

/** Refuses to start while extra monitors or screen-sharing/remote-access/recording apps are present. */
async function assertEnvironmentClean(): Promise<void> {
  const extra = screen.getAllDisplays().length - 1;
  if (extra > 0) throw new Error("Disconnect extra monitors before starting the exam.");
  const blocked = (await scanProcesses()).filter((h) => h.tier === "blocked").map((h) => h.label);
  if (blocked.length) throw new Error(`Please close ${blocked.join(", ")} before starting the exam.`);
}

function fail<T = undefined>(err: unknown): IpcResult<T> {
  return { ok: false, error: err instanceof Error ? err.message : String(err) };
}

/** Wraps a handler so any thrown error becomes `{ ok: false, error }`. */
function handle<A extends unknown[], T>(channel: string, fn: (...args: A) => Promise<T> | T): void {
  ipcMain.handle(channel, async (_event, ...args): Promise<IpcResult<T>> => {
    try {
      return { ok: true, data: await fn(...(args as A)) };
    } catch (err) {
      return fail<T>(err);
    }
  });
}

function requireSession(): StudentProfile {
  if (!session) throw new Error("Please log in first.");
  return session;
}

function registerIpc(): void {
  handle("consent:accept", () => {
    consentTimestamp = new Date().toISOString();
  });

  // The bearer token stays in the main process; the renderer only ever sees the profile.
  handle("auth:login", async (rollNumber: string, password: string, honeypot: string) => {
    const { token, ...profile } = await api.login(String(rollNumber).trim(), String(password), String(honeypot ?? ""));
    setToken(token);
    session = profile;
    return profile;
  });

  handle("auth:activate", async (rollNumber: string, email: string, honeypot: string) => {
    const { email: masked } = await api.activate(String(rollNumber).trim(), String(email).trim(), String(honeypot ?? ""));
    return { email: masked };
  });

  handle("profile:get", () => {
    requireSession();
    return api.getProfile();
  });

  handle("auth:change-password", async (currentPassword: string, newPassword: string) => {
    requireSession();
    await api.changePassword(String(currentPassword), String(newPassword));
  });

  handle("auth:logout", async () => {
    try {
      if (session) await api.logout(); // revoke the session server-side; ignore failures, we drop it locally anyway
    } catch {
      /* offline or already revoked */
    }
    setToken(null);
    session = null;
  });

  handle("exams:list", () => {
    requireSession();
    return api.listExams();
  });

  handle("exam:start", async (examId: string) => {
    const profile = requireSession();
    const config = await api.startExam(examId);

    if (config.monitoring_enabled) await assertEnvironmentClean();

    // A working camera is a precondition when the teacher requires it; the first shot doubles as the identity photo.
    const webcam = new WebcamCapturer();
    let identityPhoto: Buffer | undefined;
    if (config.monitoring_enabled && config.webcam_enabled) {
      try {
        await requestCameraAccess();
        identityPhoto = await webcam.capture();
      } catch (err) {
        webcam.dispose();
        throw new Error(`This exam requires your webcam. ${(err as Error).message}.`);
      }
    }

    // Consent was captured on the first screen; record it now that we know who/what.
    await api.postConsent(examId, consentTimestamp ?? new Date().toISOString());

    const queue = new UploadQueue(
      path.join(app.getPath("userData"), "upload-queue"),
      profile.roll_number,
      createSender(() => console.error("[sync] session rejected by server")),
    );
    await queue.init();
    const examWindow = createExamWindow(config);
    new ExamMonitor(examWindow, examId, config, queue, webcam).start(identityPhoto);
    launcherWindow?.close();
  });
}

app.whenReady().then(() => {
  configureSessions();
  registerIpc();
  createLauncherWindow();
});

app.on("window-all-closed", () => app.quit());
