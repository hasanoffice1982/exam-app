import { execFile } from "child_process";
import * as path from "path";

export type Tier = "blocked" | "watch";

export interface ProcessRule {
  id: string;
  label: string;
  tier: Tier; // blocked: refuse to start / flag loudly. watch: log only (apps that merely *can* share)
  match: RegExp; // tested against the lowercased executable name without .exe/.app
}

export interface ProcessHit {
  id: string;
  label: string;
  tier: Tier;
}

export const RULES: ProcessRule[] = [
  // Remote access / remote control
  { id: "teamviewer", label: "TeamViewer", tier: "blocked", match: /^teamviewer/ },
  { id: "anydesk", label: "AnyDesk", tier: "blocked", match: /^anydesk/ },
  { id: "parsec", label: "Parsec", tier: "blocked", match: /^parsec/ },
  { id: "rustdesk", label: "RustDesk", tier: "blocked", match: /^rustdesk/ },
  { id: "splashtop", label: "Splashtop", tier: "blocked", match: /^splashtop|^srservice$/ },
  { id: "vnc", label: "VNC", tier: "blocked", match: /^(tight|real|ultra)?vnc(server|viewer)?$|^screensharingd$|^ardagent$/ },
  { id: "chrome-remote-desktop", label: "Chrome Remote Desktop", tier: "blocked", match: /^remoting_host$|^chrome-remote-desktop/ },
  { id: "ultraviewer", label: "UltraViewer", tier: "blocked", match: /^ultraviewer/ },
  // Screen recording / capture
  { id: "obs", label: "OBS Studio", tier: "blocked", match: /^obs(64)?$|^obs-studio$|^obs-ffmpeg-mux$/ },
  { id: "screenflow", label: "ScreenFlow", tier: "blocked", match: /^screenflow/ },
  { id: "camtasia", label: "Camtasia", tier: "blocked", match: /^camtasia/ },
  { id: "bandicam", label: "Bandicam", tier: "blocked", match: /^bandicam/ },
  { id: "sharex", label: "ShareX", tier: "blocked", match: /^sharex$/ },
  { id: "loom", label: "Loom", tier: "blocked", match: /^loom$/ },
  { id: "snagit", label: "Snagit", tier: "blocked", match: /^snagit/ },
  { id: "screencapture", label: "Screen capture tool", tier: "blocked", match: /^screencapture$|^screencaptureui$/ },
  // Apps that can share a screen but are also used legitimately: logged only
  { id: "zoom", label: "Zoom", tier: "watch", match: /^zoom(\.us)?$|^cpthost$/ },
  { id: "discord", label: "Discord", tier: "watch", match: /^discord/ },
  { id: "teams", label: "Microsoft Teams", tier: "watch", match: /^(ms-)?teams$|^msteams/ },
  { id: "skype", label: "Skype", tier: "watch", match: /^skype/ },
  { id: "slack", label: "Slack", tier: "watch", match: /^slack$/ },
  { id: "webex", label: "Webex", tier: "watch", match: /^webex|^ciscocollabhost/ },
];

type Exec = (cmd: string, args: string[]) => Promise<string>;

const defaultExec: Exec = (cmd, args) =>
  new Promise((resolve, reject) =>
    execFile(cmd, args, { timeout: 8000, maxBuffer: 8 * 1024 * 1024 }, (err, stdout) => (err ? reject(err) : resolve(stdout))),
  );

/** Normalises "/Applications/OBS.app/Contents/MacOS/OBS" or "obs64.exe" to "obs" / "obs64". */
export function normalizeName(raw: string): string {
  const base = raw.includes("\\") ? raw.split("\\").pop()! : path.basename(raw);
  return base.trim().toLowerCase().replace(/\.(exe|app)$/, "");
}

export function parseProcessList(output: string, platform: NodeJS.Platform): string[] {
  const lines = output.split(/\r?\n/).filter(Boolean);
  if (platform === "win32") {
    // tasklist /fo csv /nh -> "name.exe","pid",...
    return lines.map((l) => /^"([^"]+)"/.exec(l)?.[1] ?? "").filter(Boolean).map(normalizeName);
  }
  return lines.map(normalizeName).filter(Boolean); // ps -axo comm=
}

export function findHits(names: string[]): ProcessHit[] {
  const hits = new Map<string, ProcessHit>();
  for (const name of names) {
    const rule = RULES.find((r) => r.match.test(name));
    if (rule) hits.set(rule.id, { id: rule.id, label: rule.label, tier: rule.tier });
  }
  return [...hits.values()];
}

/** Lists running processes and returns matches. Fails open ([]) if the OS call fails. */
export async function scanProcesses(exec: Exec = defaultExec, platform: NodeJS.Platform = process.platform): Promise<ProcessHit[]> {
  try {
    const output =
      platform === "win32" ? await exec("tasklist", ["/fo", "csv", "/nh"]) : await exec("ps", ["-axo", "comm="]);
    return findHits(parseProcessList(output, platform));
  } catch (err) {
    console.error("[processes] scan failed:", (err as Error).message);
    return [];
  }
}
