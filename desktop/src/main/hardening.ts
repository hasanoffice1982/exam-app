import type { BrowserWindow } from "electron";

import { EventType } from "./eventTypes";

export type AttemptKind =
  | typeof EventType.ClipboardAttempt
  | typeof EventType.DevtoolsAttempt
  | typeof EventType.BlockedShortcut
  | typeof EventType.BlockedNavigation;

export interface KeyInput {
  type: string;
  key: string;
  control: boolean;
  meta: boolean;
  shift: boolean;
  alt: boolean;
}

/** Maps a key press to the kind of blocked action it represents, or null if it is allowed. */
export function classifyShortcut(input: KeyInput): AttemptKind | null {
  if (input.type !== "keyDown") return null;
  const key = input.key.toLowerCase();
  const mod = input.control || input.meta;

  if (key === "f12") return EventType.DevtoolsAttempt;
  if (mod && input.shift && ["i", "j", "c"].includes(key)) return EventType.DevtoolsAttempt; // Ctrl+Shift+I/J/C
  if (input.meta && input.alt && ["i", "j", "c"].includes(key)) return EventType.DevtoolsAttempt; // Cmd+Opt+I/J/C

  if (mod && ["c", "x", "v"].includes(key)) return EventType.ClipboardAttempt;
  if (key === "insert" && (input.control || input.shift)) return EventType.ClipboardAttempt; // Ctrl+Insert, Shift+Insert
  if (key === "delete" && input.shift) return EventType.ClipboardAttempt; // Shift+Delete (cut)

  if (mod && ["u", "p", "s"].includes(key)) return EventType.BlockedShortcut; // view source, print, save
  return null;
}

/** A Google Form submission lands on .../formResponse; that is how we know the written part is done. */
export function isFormSubmissionUrl(url: string): boolean {
  return /^https:\/\/docs\.google\.com\/forms\/.+\/formResponse(?:[?#]|$)/.test(url);
}

/**
 * Should the locked exam window try loading the form again? Only for the first load (offline at the start, DNS
 * hiccup): once the form has shown, a failure is left alone so a half-sent submission is never silently reloaded.
 * Chromium error -3 is "aborted" (we cancelled it ourselves).
 */
export function shouldRetryLoad(failure: { errorCode: number; isMainFrame: boolean; loadedOnce: boolean }): boolean {
  return failure.isMainFrame && !failure.loadedOnce && failure.errorCode !== -3;
}

// Hosts a Google Form legitimately needs (the form itself, sign-in, assets, embedded media).
const ALLOWED_HOST_SUFFIXES = [
  "google.com",
  "gstatic.com",
  "googleapis.com",
  "googleusercontent.com",
  "forms.gle",
  "youtube.com",
  "youtube-nocookie.com",
  "ytimg.com",
];

export function isAllowedUrl(url: string, formUrl: string): boolean {
  let target: URL;
  try {
    target = new URL(url);
  } catch {
    return false;
  }
  try {
    if (target.origin === new URL(formUrl).origin) return true;
  } catch {
    /* ignore a malformed formUrl */
  }
  if (target.protocol !== "https:") return false;
  return ALLOWED_HOST_SUFFIXES.some((s) => target.hostname === s || target.hostname.endsWith(`.${s}`));
}

// Runs inside the exam page: blocks copy/cut/paste, drag/drop and the page's own context menu.
const PAGE_GUARD_JS = `(() => {
  if (window.__examGuard) return;
  window.__examGuard = true;
  window.__examEnforced = true;
  for (const type of ["copy", "cut", "paste", "contextmenu", "dragstart", "drop"]) {
    document.addEventListener(type, (e) => { if (window.__examEnforced) e.preventDefault(); }, true);
  }
})();`;

// Question text can't be drag-selected; inputs and textareas stay usable.
const PAGE_GUARD_CSS =
  "body, body * { -webkit-user-select: none !important; user-select: none !important; } " +
  "input, textarea, [contenteditable] { -webkit-user-select: text !important; user-select: text !important; }";

export interface HardeningOptions {
  formUrl: string;
  isEnforced: () => boolean;
  report: (kind: AttemptKind, detail?: string) => void;
}

/** Locks down the exam window. Returns a handle to switch enforcement on/off (teacher toggle). */
export function hardenWindow(win: BrowserWindow, opts: HardeningOptions): { setEnforced(on: boolean): void } {
  const wc = win.webContents;

  wc.on("before-input-event", (event, input) => {
    if (!opts.isEnforced()) return;
    const kind = classifyShortcut(input);
    if (kind) {
      event.preventDefault();
      opts.report(kind, input.key);
    }
  });

  const guardNavigation = (event: { preventDefault(): void }, url: string) => {
    if (isAllowedUrl(url, opts.formUrl)) return;
    event.preventDefault();
    opts.report(EventType.BlockedNavigation, new URL(url, "about:blank").hostname || url.slice(0, 100));
  };
  wc.on("will-navigate", guardNavigation);
  wc.on("will-redirect", guardNavigation);

  wc.setWindowOpenHandler(({ url }) => {
    if (isAllowedUrl(url, opts.formUrl)) void win.loadURL(url);
    else opts.report(EventType.BlockedNavigation, url.slice(0, 100));
    return { action: "deny" };
  });

  wc.on("devtools-opened", () => {
    wc.closeDevTools();
    opts.report(EventType.DevtoolsAttempt, "opened");
  });

  wc.on("dom-ready", () => {
    void wc.executeJavaScript(PAGE_GUARD_JS).catch(() => undefined);
    void wc.insertCSS(PAGE_GUARD_CSS).catch(() => undefined);
  });

  return {
    setEnforced(on: boolean) {
      void wc.executeJavaScript(`window.__examEnforced = ${on};`).catch(() => undefined);
    },
  };
}
