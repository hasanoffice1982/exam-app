// Run: npx electron scripts/stage-smoke.js
// Starts the real app against a fake server, logs in, starts an exam with a written + practical part, then flips the
// server-side stage to "practical" (what the teacher's "To practical" button does) and checks the window hand-over.
const { app, BrowserWindow } = require("electron");
const fs = require("fs");
const os = require("os");
const path = require("path");

app.setPath("userData", fs.mkdtempSync(path.join(os.tmpdir(), "stage-smoke-")));
const realSetInterval = global.setInterval;
global.setInterval = (fn, ms, ...rest) => realSetInterval(fn, ms === 120000 ? 400 : ms, ...rest); // config poll every 0.4 s

const calls = [];
let stage = "written";
const config = () => ({
  name: "Physics Lab", monitoring_enabled: false, form_url: "data:text/html,<h1>the form</h1>", written_enabled: true,
  practical_enabled: true, practical_instructions: "Build the circuit.\nPhoto not needed.", practical_url: "https://example.com/task",
  practical_screenshot_seconds: 60, stage, starts_at: null, ends_at: null, grace_seconds: 3, webcam_enabled: false,
  webcam_interval_seconds: 180, status: "open", server_time: new Date().toISOString(),
});
const json = (body, status = 200) => new Response(JSON.stringify(body), { status });
global.fetch = async (url, init = {}) => {
  const p = new URL(url).pathname;
  calls.push(`${init.method || "GET"} ${p}`);
  if (p === "/api/login/") return json({ roll_number: "1", name: "Ann", token: "t", batch: 81 });
  if (p === "/api/exams/") return json([{ exam_id: "lab", name: "Physics Lab", starts_at: null, ends_at: null, status: "open" }]);
  if (p === "/api/exams/lab/start/" || p === "/api/config/lab/") return json(config());
  if (p === "/api/exams/lab/advance/") { stage = "practical"; return json(config()); }
  return json({});
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const windows = () => BrowserWindow.getAllWindows().filter((w) => !w.isDestroyed());
const describe = () => windows().map((w) => `${w.isFullScreen() ? "fullscreen " : ""}${w.webContents.getURL().split("/").pop().slice(0, 30)}`);

require("../build/main/index.js");
app.whenReady().then(async () => {
  await sleep(1200);
  const launcher = windows()[0];
  const js = (code, wc = launcher.webContents) => wc.executeJavaScript(code);
  const out = { start: describe() };
  await js(`document.getElementById("start-btn").click()`); await sleep(150);
  await js(`document.getElementById("roll").value="1"; document.getElementById("password").value="pw"; document.getElementById("login-form").requestSubmit()`); await sleep(600);
  await js(`document.getElementById("exam").value="lab"; document.getElementById("exam-form").requestSubmit()`); await sleep(1500);
  out.afterStart = describe();
  out.writtenWindowIsFullscreen = windows().some((w) => w.isFullScreen());
  stage = "practical"; // the teacher presses "To practical" (or the student submitted the form)
  await sleep(4500);
  out.afterHandOver = describe();
  const practical = windows().find((w) => w.webContents.getURL().endsWith("practical.html"));
  if (practical) {
    out.practicalIsFullscreen = practical.isFullScreen();
    out.practicalPage = await js(`({ name: document.getElementById("exam-name").textContent, instructions: document.getElementById("instructions").textContent, linkVisible: !document.getElementById("open-link").hidden, timer: document.getElementById("timer").textContent, note: document.getElementById("note").textContent })`, practical.webContents);
  }
  out.appStillRunning = windows().length === 1;
  out.calls = [...new Set(calls)];
  console.log("RESULT", JSON.stringify(out));
  app.exit(0);
});
