// Run (two phases, two processes):
//   cd desktop && BACKEND_URL=http://127.0.0.1:8780 npx electron ../manuals/src/capture-app.js a
//   cd desktop && BACKEND_URL=http://127.0.0.1:8780 npx electron ../manuals/src/capture-app.js b
// Drives the REAL student app against the demo server and saves annotated screenshots of every screen.
const { app, BrowserWindow } = require("electron");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { makeWindow, shot, annotate, clearMarks, sleep } = require("./lib");

const phase = process.argv.find((a) => a === "a" || a === "b") || "a";
const OUT = path.join(__dirname, "..", "images", "student");
app.setPath("userData", fs.mkdtempSync(path.join(os.tmpdir(), "student-manual-")));
const missing = [];

require("../../desktop/build/main/index.js"); // the real app

const windows = () => BrowserWindow.getAllWindows().filter((w) => !w.isDestroyed());
const js = (win, code) => win.webContents.executeJavaScript(code);
const click = (win, id) => js(win, `document.getElementById("${id}").click()`);
const fill = (win, id, v) => js(win, `document.getElementById("${id}").value = ${JSON.stringify(v)}`);

async function snap(win, name, marks = [], opts = {}) {
  await win.webContents.insertCSS("::-webkit-scrollbar { display: none; }").catch(() => undefined);
  await clearMarks(win);
  if (marks.length) {
    await annotate(win, marks);
    const present = await js(win, `[...document.querySelectorAll('[data-mark=badge]')].map((b) => Number(b.textContent))`);
    for (const m of marks) if (!present.includes(m.n)) missing.push(`${name}: mark ${m.n} (${m.sel || m.text})`);
  }
  await shot(win, path.join(OUT, `${name}.png`), { outWidth: 1100, settle: 250, ...opts });
  console.log("saved", `student/${name}.png`);
}

async function login(win, roll, password) {
  await fill(win, "roll", roll);
  await fill(win, "password", password);
  await js(win, `document.getElementById("login-form").requestSubmit()`);
  await sleep(900);
}

async function phaseA() {
  const win = windows()[0];
  await sleep(1200);
  await snap(win, "01-consent", [{ sel: "#start-btn", n: 1 }]);
  await click(win, "start-btn"); await sleep(250);
  await snap(win, "02-login", [{ sel: "#roll", n: 1 }, { sel: "#password", n: 2 }, { sel: "#login-btn", n: 3 }, { sel: "#to-activate", n: 4 }]);

  await fill(win, "roll", "81009"); await fill(win, "password", "wrong-password");
  await js(win, `document.getElementById("login-form").requestSubmit()`); await sleep(900);
  await snap(win, "03-login-error", [{ sel: "#error", n: 1 }]);

  await click(win, "to-activate"); await sleep(200);
  await fill(win, "a-roll", "81010"); await fill(win, "a-email", "81010@school.example");
  await snap(win, "04-activate", [{ sel: "#a-roll", n: 1 }, { sel: "#a-email", n: 2 }, { sel: "#activate-btn", n: 3 }, { sel: "#to-login", n: 4 }]);

  await click(win, "to-login"); await sleep(200);
  await login(win, "81009", "Demo-pass-1");
  await js(win, `(() => { const s = document.getElementById("exam"); s.value = "physics-mid"; s.dispatchEvent(new Event("change", { bubbles: true })); })()`);
  await sleep(200);
  await snap(win, "05-exam-list", [{ sel: "#to-profile", n: 1 }, { sel: "#exam", n: 2 }, { sel: "#exam-time", n: 3 }, { sel: "#begin-btn", n: 4 }]);

  await click(win, "to-profile"); await sleep(700);
  await fill(win, "pw-current", "Demo-pass-1"); await fill(win, "pw-new", "My-new-pass-7"); await fill(win, "pw-confirm", "My-new-pass-7");
  await snap(win, "06-profile", [{ sel: ".profile", n: 1 }, { sel: "#password-form", n: 2 }, { sel: "#profile-back", n: 3 }]);

  await click(win, "profile-back"); await sleep(800);
  await js(win, `(() => { const s = document.getElementById("exam"); s.value = "physics-mid"; s.dispatchEvent(new Event("change", { bubbles: true })); })()`);
  await js(win, `document.getElementById("exam-form").requestSubmit()`);
  await sleep(4500); // the exam window goes full screen
  const exam = windows().find((w) => w.webContents.getURL().includes("8781"));
  if (exam) await snap(exam, "07-written-window", [], { outWidth: 1400 });
  else missing.push("07-written-window: exam window did not open");
}

async function phaseB() {
  const win = windows()[0];
  await sleep(1200);
  await click(win, "start-btn"); await sleep(250);
  await login(win, "81001", "Demo-pass-1");
  await js(win, `(() => { const s = document.getElementById("exam"); s.value = "physics-mid"; s.dispatchEvent(new Event("change", { bubbles: true })); })()`);
  await js(win, `document.getElementById("exam-form").requestSubmit()`);
  await sleep(4000);
  const practical = windows().find((w) => w.webContents.getURL().endsWith("practical.html"));
  if (practical) {
    practical.setContentSize(540, 660);
    await sleep(500);
    await snap(practical, "08-practical-window", [
      { sel: "#timer", n: 1 }, { sel: "#note", n: 2 }, { sel: "#instructions-card", n: 3 }, { sel: "#open-link", n: 4 }, { sel: "#finish", n: 5 },
    ]);
  } else missing.push("08-practical-window: practical window did not open");
}

app.whenReady().then(async () => {
  try { await (phase === "a" ? phaseA() : phaseB()); } catch (err) { console.error("CAPTURE FAILED", err); process.exitCode = 1; }
  console.log(missing.length ? "MISSING:\n" + missing.join("\n") : "all marks placed");
  app.exit(process.exitCode || 0);
});
