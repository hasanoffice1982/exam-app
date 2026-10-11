import assert from "node:assert/strict";
import { test } from "node:test";

import { findHits, normalizeName, parseProcessList, scanProcesses } from "./processes";

const MAC_PS = `/sbin/launchd
/Applications/OBS.app/Contents/MacOS/OBS
/Applications/zoom.us.app/Contents/MacOS/zoom.us
/Applications/Obsidian.app/Contents/MacOS/Obsidian
/Applications/Google Chrome.app/Contents/MacOS/Google Chrome
/System/Library/CoreServices/screensharingd`;

const WIN_TASKLIST = `"System Idle Process","0","Services","0","8 K"
"obs64.exe","4120","Console","1","210,000 K"
"TeamViewer_Service.exe","900","Services","0","20,000 K"
"chrome.exe","111","Console","1","300,000 K"
"Obsidian.exe","222","Console","1","90,000 K"`;

test("normalizeName handles mac paths and windows executables", () => {
  assert.equal(normalizeName("/Applications/OBS.app/Contents/MacOS/OBS"), "obs");
  assert.equal(normalizeName("obs64.exe"), "obs64");
  assert.equal(normalizeName("C:\\Program Files\\AnyDesk\\AnyDesk.exe"), "anydesk");
});

test("macOS ps output: finds OBS and screensharingd, not Obsidian or Chrome", () => {
  const hits = findHits(parseProcessList(MAC_PS, "darwin"));
  assert.deepEqual(hits.map((h) => h.id).sort(), ["obs", "vnc", "zoom"]);
  assert.equal(hits.find((h) => h.id === "obs")?.tier, "blocked");
  assert.equal(hits.find((h) => h.id === "zoom")?.tier, "watch");
});

test("Windows tasklist output: finds OBS and TeamViewer, not Obsidian or Chrome", () => {
  const hits = findHits(parseProcessList(WIN_TASKLIST, "win32"));
  assert.deepEqual(hits.map((h) => h.id).sort(), ["obs", "teamviewer"]);
});

test("a clean machine produces no hits", () => {
  assert.deepEqual(findHits(parseProcessList("/sbin/launchd\n/usr/sbin/cfprefsd", "darwin")), []);
});

test("duplicate processes of the same app are reported once", () => {
  assert.equal(findHits(["obs", "obs", "obs-ffmpeg-mux"]).length, 1);
});

test("scanProcesses uses ps on unix and tasklist on windows", async () => {
  const calls: string[] = [];
  const exec = async (cmd: string) => {
    calls.push(cmd);
    return cmd === "ps" ? MAC_PS : WIN_TASKLIST;
  };
  assert.equal((await scanProcesses(exec, "darwin")).length, 3);
  assert.equal((await scanProcesses(exec, "win32")).length, 2);
  assert.deepEqual(calls, ["ps", "tasklist"]);
});

test("scanProcesses fails open when the OS command fails", async () => {
  const exec = async () => {
    throw new Error("boom");
  };
  assert.deepEqual(await scanProcesses(exec, "darwin"), []);
});
