import { randomUUID } from "crypto";
import { BrowserWindow, clipboard, dialog, screen } from "electron";

import { api, ApiError, isRetryable } from "./api";
import { EventType, EventTypeValue } from "./eventTypes";
import { CONFIG_POLL_INTERVAL_MS, HEARTBEAT_INTERVAL_MS, PROCESS_SCAN_INTERVAL_MS, SCREENSHOT_DELAY_MS } from "./config";
import { GraceTimer } from "./grace";
import { AttemptKind, hardenWindow, isFormSubmissionUrl } from "./hardening";
import { AttemptLimiter } from "./limiter";
import { scanProcesses } from "./processes";
import { nextDelayMs, friendlyCameraError } from "./webcamUtils";
import type { WebcamCapturer } from "./webcam";
import { UploadQueue } from "./queue";
import { captureScreen } from "./screenshot";

export interface MonitorOptions {
  /** Written part finished (or a teacher moved the student on): open the practical part. Resolves when it is up. */
  onAdvance?: (config?: ExamConfig) => Promise<void>;
}

const MIN_PRACTICAL_SHOT_SECONDS = 15;

/**
 * Watches one exam window and reports to the backend. Written part: locked full-screen Google Form, blur and
 * clipboard enforcement. Practical part: a free window, screenshots on a timer, no blur penalty.
 */
export class ExamMonitor {
  private monitoringEnabled: boolean;
  private awayRecorded = false;
  private dialogOpen = false;
  private quitting = false;
  private offline = false;
  private endsAt: number | null = null; // local-clock ms
  private endTimer?: NodeJS.Timeout;
  private pollTimer?: NodeJS.Timeout;
  private heartbeatTimer?: NodeJS.Timeout;
  private scanTimer?: NodeJS.Timeout;
  private webcamTimer?: NodeJS.Timeout;
  private webcamEnabled = false;
  private webcamIntervalSeconds = 180;
  private readonly practical: boolean;
  private practicalTimer?: NodeJS.Timeout;
  private practicalShotSeconds: number;
  private formSubmitted = false;
  private handingOver = false;
  private handedOver = false;
  private knownHits = new Set<string>();
  private hardening?: { setEnforced(on: boolean): void };
  private readonly limiter = new AttemptLimiter();
  private readonly grace: GraceTimer;

  constructor(
    private readonly win: BrowserWindow,
    private readonly examId: string,
    private readonly config: ExamConfig,
    private readonly queue: UploadQueue,
    private readonly webcam: WebcamCapturer,
    private readonly options: MonitorOptions = {},
  ) {
    this.practical = config.stage === "practical";
    this.practicalShotSeconds = config.practical_screenshot_seconds;
    this.monitoringEnabled = config.monitoring_enabled;
    this.grace = new GraceTimer(config.grace_seconds * 1000);
    this.applySchedule(config);
  }

  /** `identityPhoto` is the webcam shot taken at login-to-exam time, queued as the first photo. */
  start(identityPhoto?: Buffer): void {
    if (identityPhoto) void this.queueWebcamPhoto(identityPhoto, new Date().toISOString());
    this.applyWebcamConfig(this.config);
    this.win.setContentProtection(this.monitoringEnabled); // screenshots/recordings/screen-share show the window as black
    screen.on("display-added", this.onDisplayAdded);
    this.scanTimer = setInterval(() => void this.scanApps(), PROCESS_SCAN_INTERVAL_MS);
    if (this.practical) this.startPractical();
    else this.startWritten();
    this.win.on("closed", () => {
      this.grace.cancel();
      clearInterval(this.pollTimer);
      clearInterval(this.heartbeatTimer);
      clearTimeout(this.endTimer);
      clearInterval(this.scanTimer);
      clearTimeout(this.webcamTimer);
      clearTimeout(this.practicalTimer);
      this.webcam.dispose();
      screen.removeListener("display-added", this.onDisplayAdded);
      if (!this.handedOver) this.queue.stopTimer(); // the next part keeps using the same queue
    });
    this.pollTimer = setInterval(() => void this.refreshConfig(), CONFIG_POLL_INTERVAL_MS);
    this.heartbeatTimer = setInterval(() => void this.heartbeat(), HEARTBEAT_INTERVAL_MS);
    this.queue.startTimer(15_000);
    void this.queue.flush(); // deliver anything left over from an earlier run
  }

  /** Written part: lock the window down and watch for leaving it. */
  private startWritten(): void {
    clipboard.clear(); // nothing copied before the exam can be pasted into it
    this.hardening = hardenWindow(this.win, {
      formUrl: this.config.form_url,
      isEnforced: () => this.monitoringEnabled,
      report: (kind, detail) => this.reportAttempt(kind, detail),
    });
    this.win.webContents.on("did-navigate", (_event, url) => {
      if (isFormSubmissionUrl(url)) void this.onFormSubmitted();
    });
    this.win.on("blur", () => this.onBlur());
    this.win.on("focus", () => void this.onFocus());
    this.win.on("leave-full-screen", () => void this.onLeaveFullScreen());
    this.win.on("close", (event) => {
      if (this.quitting) return;
      event.preventDefault();
      void this.confirmQuit("Do you want to quit the exam?");
    });
  }

  /** Practical part: the student works in other apps, so switching away is normal; we sample the screen instead. */
  private startPractical(): void {
    this.schedulePracticalShot();
    this.win.on("close", (event) => {
      if (this.quitting) return;
      event.preventDefault();
      void this.confirmFinishPractical();
    });
  }

  // ---- schedule ----------------------------------------------------------------------------

  /** Uses the server's clock so a wrong student clock can't extend the exam. */
  private applySchedule(config: ExamConfig): void {
    clearTimeout(this.endTimer);
    this.grace.setGraceMs(config.grace_seconds * 1000);
    if (!config.ends_at) {
      this.endsAt = null;
      return;
    }
    const offset = Date.parse(config.server_time) - Date.now();
    this.endsAt = Date.parse(config.ends_at) - offset;
    const delay = Math.min(Math.max(this.endsAt - Date.now(), 0), 2 ** 31 - 1);
    this.endTimer = setTimeout(() => void this.onTimeUp(), delay);
  }

  private async onTimeUp(): Promise<void> {
    if (this.quitting || this.win.isDestroyed()) return;
    if (this.endsAt && this.endsAt > Date.now() + 1000) return; // clamped timer fired early
    await this.finish(EventType.TimeUp, "Time is up. The exam has ended.", "This window will now close.");
  }

  // ---- background tasks --------------------------------------------------------------------

  private async refreshConfig(): Promise<void> {
    try {
      const config = await api.getConfig(this.examId);
      this.monitoringEnabled = config.monitoring_enabled;
      this.hardening?.setEnforced(config.monitoring_enabled);
      if (!this.win.isDestroyed()) this.win.setContentProtection(config.monitoring_enabled);
      this.applyWebcamConfig(config);
      this.practicalShotSeconds = config.practical_screenshot_seconds;
      this.applySchedule(config); // teacher may have extended or shortened the exam
      if (!this.practical && config.stage === "practical") void this.handOver(config); // a teacher moved this student on
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return void this.sessionEnded();
      this.log("config poll failed", err);
    }
  }

  private async heartbeat(): Promise<void> {
    try {
      await api.heartbeat();
      if (this.offline) {
        this.offline = false;
        await this.record(EventType.ConnectionRestored);
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return void this.sessionEnded();
      if (isRetryable(err) && !this.offline) {
        this.offline = true;
        await this.record(EventType.ConnectionLost); // queued; delivered once the network is back
      }
    }
  }

  private async sessionEnded(): Promise<void> {
    await this.finish(
      null,
      "Your session has ended.",
      "You logged in elsewhere or your teacher ended your session. The exam window will close.",
    );
  }

  /** Shows a final message, optionally logs an event, then closes the exam for good. */
  private async finish(eventType: EventTypeValue | null, message: string, detail: string): Promise<void> {
    if (this.quitting) return;
    this.quitting = true;
    if (eventType) await this.record(eventType);
    if (this.win.isDestroyed()) return;
    await dialog.showMessageBox(this.win, { type: "info", title: "Exam", message, detail });
    if (!this.win.isDestroyed()) this.win.close();
  }

  // ---- window events -----------------------------------------------------------------------

  private onBlur(): void {
    if (this.dialogOpen || this.quitting) return;
    const timestamp = new Date().toISOString();
    this.grace.start(() => void this.handleAway(timestamp));
  }

  private async handleAway(timestamp: string): Promise<void> {
    if (this.dialogOpen || this.quitting || !this.monitoringEnabled) return;
    this.awayRecorded = true;
    await Promise.allSettled([this.record(EventType.TabSwitch, timestamp), this.captureAndQueue(timestamp)]);
  }

  private async onFocus(): Promise<void> {
    this.grace.cancel(); // came back inside the grace period: nothing happened
    if (this.monitoringEnabled) clipboard.clear(); // drop anything copied while away
    if (this.dialogOpen || this.quitting || !this.awayRecorded) return;
    this.awayRecorded = false;
    await this.record(EventType.ReturnedToExam);
    await this.confirmQuit("You switched away from the exam window.");
  }

  private async onLeaveFullScreen(): Promise<void> {
    if (this.dialogOpen || this.quitting || !this.monitoringEnabled) return;
    await this.record(EventType.ExitedFullscreen);
    setTimeout(() => !this.win.isDestroyed() && this.win.setFullScreen(true), 200);
    await this.confirmQuit("You left full-screen mode.");
  }

  /** Runs a dialog with the guard that ignores the blur/focus noise dialogs themselves cause. */
  private async withDialog<T>(show: () => Promise<T>): Promise<T | undefined> {
    if (this.dialogOpen || this.quitting || this.win.isDestroyed()) return undefined;
    this.dialogOpen = true;
    try {
      return await show();
    } finally {
      setTimeout(() => (this.dialogOpen = false), 500);
    }
  }

  /** Asks the student whether to quit; quitting is logged and closes the exam. */
  private async confirmQuit(reason: string): Promise<void> {
    const result = await this.withDialog(() =>
      dialog.showMessageBox(this.win, {
        type: "warning",
        title: "Exam warning",
        message: `${reason} Would you like to quit the exam?`,
        detail: "If you quit the exam, you will be marked 0.",
        buttons: ["Return to exam", "Quit exam"],
        defaultId: 0,
        cancelId: 0,
        noLink: true,
      }),
    );
    if (result?.response === 1) {
      this.quitting = true;
      await this.record(EventType.ExamQuit);
      this.win.close();
    }
  }

  // ---- written -> practical ----------------------------------------------------------------

  /** The Google Form was submitted: either move on to the practical part or finish. */
  private async onFormSubmitted(): Promise<void> {
    if (this.formSubmitted || this.quitting) return;
    this.formSubmitted = true;
    await this.record(EventType.WrittenSubmitted);
    if (this.config.practical_enabled && this.options.onAdvance) {
      await this.withDialog(() =>
        dialog.showMessageBox(this.win, {
          type: "info",
          title: "Written part submitted",
          message: "Your written answers were submitted.",
          detail: "Next comes the practical part. Click the button to start it.",
          buttons: ["Start practical part"],
          defaultId: 0,
          noLink: true,
        }),
      );
      await this.handOver();
      return;
    }
    await this.record(EventType.ExamFinished);
    await this.finish(null, "Your answers were submitted.", "You can close this window. Good luck!");
  }

  /** Opens the practical part (asking the server unless a config is already known), then closes this window. */
  private async handOver(known?: ExamConfig): Promise<void> {
    if (this.handingOver || !this.options.onAdvance) return;
    this.handingOver = true;
    for (;;) {
      try {
        this.handedOver = true; // before the new window exists, so our queue timer isn't stopped under it
        await this.options.onAdvance(known);
        break;
      } catch (err) {
        this.handedOver = false;
        this.log("could not start the practical part", err);
        this.dialogOpen = false;
        await this.withDialog(() =>
          dialog.showMessageBox(this.win, {
            type: "warning",
            title: "Practical part",
            message: "Could not start the practical part.",
            detail: "Check your connection, then try again. Your written answers are already submitted.",
            buttons: ["Try again"],
            defaultId: 0,
            noLink: true,
          }),
        );
      }
    }
    this.quitting = true;
    if (!this.win.isDestroyed()) this.win.close();
  }

  // ---- practical ---------------------------------------------------------------------------

  /** Called from the practical window's Finish button (and when the window is closed). */
  finishPractical(): Promise<void> {
    return this.confirmFinishPractical();
  }

  private async confirmFinishPractical(): Promise<void> {
    const result = await this.withDialog(() =>
      dialog.showMessageBox(this.win, {
        type: "question",
        title: "Finish practical",
        message: "Finish the practical part now?",
        detail: "Make sure your work is saved and handed in as your teacher instructed. You cannot come back after finishing.",
        buttons: ["Keep working", "Finish"],
        defaultId: 0,
        cancelId: 0,
        noLink: true,
      }),
    );
    if (result?.response === 1) {
      this.quitting = true;
      await this.record(EventType.ExamFinished);
      if (!this.win.isDestroyed()) this.win.close();
    }
  }

  private schedulePracticalShot(): void {
    this.practicalTimer = setTimeout(async () => {
      if (this.monitoringEnabled && !this.quitting) await this.capturePracticalShot();
      if (!this.quitting) this.schedulePracticalShot();
    }, nextDelayMs(this.practicalShotSeconds, Math.random, MIN_PRACTICAL_SHOT_SECONDS));
  }

  private async capturePracticalShot(): Promise<void> {
    try {
      const jpeg = await captureScreen(this.win, "cursor");
      await this.queue.enqueue(
        { id: randomUUID(), kind: "screenshot", fields: { exam_id: this.examId, timestamp: new Date().toISOString() } },
        jpeg,
        "jpg",
      );
      void this.queue.flush();
    } catch (err) {
      this.log("practical screenshot failed", err);
    }
  }

  // ---- webcam ------------------------------------------------------------------------------

  /** Starts/stops the random-interval photo loop when the teacher toggles it. */
  private applyWebcamConfig(config: ExamConfig): void {
    this.webcamIntervalSeconds = config.webcam_interval_seconds;
    const enable = config.monitoring_enabled && config.webcam_enabled;
    if (enable && !this.webcamEnabled) this.scheduleWebcam();
    if (!enable) clearTimeout(this.webcamTimer);
    this.webcamEnabled = enable;
  }

  private scheduleWebcam(): void {
    this.webcamTimer = setTimeout(async () => {
      await this.takeWebcamPhoto();
      if (this.webcamEnabled && !this.quitting) this.scheduleWebcam();
    }, nextDelayMs(this.webcamIntervalSeconds));
  }

  private async takeWebcamPhoto(): Promise<void> {
    const timestamp = new Date().toISOString();
    try {
      await this.queueWebcamPhoto(await this.webcam.capture(), timestamp);
    } catch (err) {
      const reason = friendlyCameraError(err instanceof Error ? err.message : String(err));
      if (this.limiter.allow(EventType.CameraUnavailable)) await this.record(EventType.CameraUnavailable, timestamp, reason);
    }
  }

  private async queueWebcamPhoto(jpeg: Buffer, timestamp: string): Promise<void> {
    await this.queue.enqueue(
      { id: randomUUID(), kind: "screenshot", fields: { exam_id: this.examId, timestamp, kind: "webcam" } },
      jpeg,
      "jpg",
    );
    void this.queue.flush();
  }

  // ---- anti-cheat ----------------------------------------------------------------------------

  private reportAttempt(kind: AttemptKind, detail?: string): void {
    if (this.limiter.allow(kind)) void this.record(kind, undefined, detail);
  }

  private onDisplayAdded = (): void => {
    if (!this.monitoringEnabled || this.quitting) return;
    const count = screen.getAllDisplays().length;
    void this.record(EventType.DisplayAdded, undefined, `${count} displays`);
    if (this.practical) return; // practical work may legitimately use a second screen: logged only
    void this.notify("An extra display was detected.", "Disconnect the additional monitor now. This has been recorded.");
  };

  /** Flags newly appeared screen-sharing / remote-access / recording apps. */
  private async scanApps(): Promise<void> {
    if (!this.monitoringEnabled || this.quitting) return;
    const hits = await scanProcesses();
    const current = new Set(hits.map((h) => h.id));
    const fresh = hits.filter((h) => !this.knownHits.has(h.id));
    this.knownHits = current;
    for (const hit of fresh) {
      await this.record(hit.tier === "blocked" ? EventType.BlockedAppDetected : EventType.WatchAppDetected, undefined, hit.label);
    }
    const blocked = fresh.filter((h) => h.tier === "blocked").map((h) => h.label);
    if (blocked.length) {
      await this.notify(`Please close ${blocked.join(", ")}.`, "Screen sharing, recording and remote-access apps are not allowed during the exam. This has been recorded.");
    }
  }

  private async notify(message: string, detail: string): Promise<void> {
    await this.withDialog(() => dialog.showMessageBox(this.win, { type: "warning", title: "Exam notice", message, detail }));
  }

  // ---- reporting ---------------------------------------------------------------------------

  private async record(eventType: EventTypeValue, timestamp = new Date().toISOString(), detail?: string): Promise<void> {
    try {
      const fields: Record<string, string> = { exam_id: this.examId, event_type: eventType, timestamp };
      if (detail) fields.detail = detail.slice(0, 200);
      await this.queue.enqueue({ id: randomUUID(), kind: "event", fields });
      void this.queue.flush();
    } catch (err) {
      this.log("event failed", err);
    }
  }

  private async captureAndQueue(timestamp: string): Promise<void> {
    try {
      await new Promise((r) => setTimeout(r, SCREENSHOT_DELAY_MS));
      const jpeg = await captureScreen(this.win);
      await this.queue.enqueue(
        { id: randomUUID(), kind: "screenshot", fields: { exam_id: this.examId, timestamp } },
        jpeg,
        "jpg",
      );
      void this.queue.flush();
    } catch (err) {
      this.log("screenshot failed", err);
    }
  }

  // Never surface errors to the student; log to the console only.
  private log(msg: string, err: unknown): void {
    console.error(`[monitor] ${msg}:`, err instanceof Error ? err.message : err);
  }
}
