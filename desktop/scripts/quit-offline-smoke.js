// Run: npx electron scripts/quit-offline-smoke.js
// A student quit while offline, so "exam_quit" is still waiting in the upload queue. On the next start the app must
// deliver it BEFORE asking the server to start the exam, so the server refuses instead of letting them back in.
const { app, BrowserWindow } = require("electron");
const fs = require("fs");
const os = require("os");
const path = require("path");

const userData = fs.mkdtempSync(path.join(os.tmpdir(), "quit-smoke-"));
app.setPath("userData", userData);
fs.mkdirSync(path.join(userData, "upload-queue", "files"), { recursive: true });
fs.writeFileSync(path.join(userData, "upload-queue", "queue.json"), JSON.stringify([
  { id: "11111111-1111-4111-8111-111111111111", owner: "1", kind: "event",
    fields: { exam_id: "lab", event_type: "exam_quit", timestamp: new Date().toISOString() } },
]));

const calls = [];
let quit = false;
const json = (body, status = 200) => new Response(JSON.stringify(body), { status });
global.fetch = async (url, init = {}) => {
  const p = new URL(url).pathname;
  calls.push(`${init.method || "GET"} ${p}`);
  if (p === "/api/login/") return json({ roll_number: "1", name: "Ann", token: "t", batch: 81 });
  if (p === "/api/exams/") return json([{ exam_id: "lab", name: "Lab", starts_at: null, ends_at: null, status: "open" }]);
  if (p === "/api/events/") { quit = JSON.parse(init.body).event_type === "exam_quit"; return json({}, 201); }
  if (p === "/api/exams/lab/start/") return quit ? json({ detail: "You quit this exam and cannot re-enter it." }, 403) : json({ stage: "written" });
  return json({});
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
require("../build/main/index.js");
app.whenReady().then(async () => {
  await sleep(1200);
  const win = BrowserWindow.getAllWindows()[0];
  const js = (c) => win.webContents.executeJavaScript(c);
  await js(`document.getElementById("start-btn").click()`); await sleep(150);
  await js(`document.getElementById("roll").value="1"; document.getElementById("password").value="pw"; document.getElementById("login-form").requestSubmit()`); await sleep(600);
  await js(`document.getElementById("exam").value="lab"; document.getElementById("exam-form").requestSubmit()`); await sleep(2500);
  const out = {
    error: await js(`document.getElementById("error").textContent`),
    windows: BrowserWindow.getAllWindows().length,
    eventBeforeStart: calls.indexOf("POST /api/events/") !== -1 && calls.indexOf("POST /api/events/") < calls.indexOf("POST /api/exams/lab/start/"),
    queueLeft: JSON.parse(fs.readFileSync(path.join(userData, "upload-queue", "queue.json"), "utf8")).length,
    calls,
  };
  console.log("RESULT", JSON.stringify(out));
  app.exit(0);
});
