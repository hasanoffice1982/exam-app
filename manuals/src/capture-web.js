// Run: cd desktop && DEMO_URL=http://127.0.0.1:8780 npx electron ../manuals/src/capture-web.js
// Takes the annotated admin and teacher screenshots from the demo server.
const { app, session } = require("electron");
const path = require("path");
const { makeWindow, shot, annotate, clearMarks, sleep } = require("./lib");

const BASE = process.env.DEMO_URL || "http://127.0.0.1:8780";
const OUT = path.join(__dirname, "..", "images");
const missing = [];

async function go(win, url, wait = 500) {
  await win.loadURL(BASE + url);
  await win.webContents.insertCSS("::-webkit-scrollbar { display: none; }"); // no scrollbars in the screenshots
  await sleep(wait);
}
const js = (win, code) => win.webContents.executeJavaScript(code);

async function login(win, loginUrl, user, password) {
  await go(win, loginUrl);
  await js(win, `document.querySelector('input[name=username]').value=${JSON.stringify(user)}; document.querySelector('input[name=password]').value=${JSON.stringify(password)};`);
  const loaded = new Promise((r) => win.webContents.once("did-finish-load", r));
  await js(win, `document.querySelector('form').submit()`);
  await loaded;
  await sleep(500);
}

/** Annotate, capture, and note any call-out whose element was not found (so the script tells us what to fix). */
async function snap(win, role, name, marks = [], opts = {}) {
  if (role === "admin" && !name.includes("login") && !name.includes("password-sheet")) opts = { ignoreLeft: 255, ...opts };
  await clearMarks(win);
  if (role === "admin") await js(win, `document.querySelectorAll('footer').forEach((f) => (f.style.display = 'none'))`); // lets the blank band under the content be trimmed
  await annotateReport(win, name, marks);
  await shot(win, path.join(OUT, role, `${name}.png`), opts);
  console.log("saved", `${role}/${name}.png`);
}

async function annotateReport(win, name, marks) {
  if (!marks.length) return;
  await annotate(win, marks);
  const present = await js(win, `[...document.querySelectorAll('[data-mark=badge]')].map((b) => Number(b.textContent))`);
  for (const m of marks) if (!present.includes(m.n)) missing.push(`${name}: mark ${m.n} (${m.sel || m.text})`);
  const where = await js(win, `(() => { const H = Math.max(document.documentElement.scrollHeight, document.body.scrollHeight); return [...document.querySelectorAll('[data-mark=badge]')].map((b) => b.textContent + '@' + (parseFloat(b.style.top) / H).toFixed(2)).join(' '); })()`);
  console.log("  marks", name, where);
}

async function main() {
  // ---------------------------------------------------------------- ADMIN
  const adminWin = makeWindow(1180, 780, { webPreferences: { partition: "demo-admin" } });
  await go(adminWin, "/admin/login/");
  await snap(adminWin, "admin", "01-login", [
    { sel: "input[name=username]", n: 1 }, { sel: "input[name=password]", n: 2 }, { sel: "button[type=submit]", n: 3 },
  ], { fullPage: false });
  await login(adminWin, "/admin/login/", "admin", "Admin-demo-1");

  await go(adminWin, "/admin/");
  await snap(adminWin, "admin", "02-dashboard", [
    { sel: '.app-sidebar a[href="/admin/proctoring/exam/"]', n: 1 }, { sel: '.app-sidebar a[href="/admin/proctoring/student/"]', n: 2 },
    { sel: '.app-sidebar a[href="/admin/proctoring/examattempt/"]', n: 3 }, { sel: '.app-sidebar a[href="/admin/auth/user/"]', n: 4 },
    { sel: 'input[placeholder*="Students"]', n: 5, side: "br" },
  ]);

  await go(adminWin, "/admin/proctoring/student/");
  await snap(adminWin, "admin", "03-students-list", [
    { text: "Add student", tag: "a", n: 1 }, { sel: ".select2-container", n: 2 }, { text: "Batch", tag: "th", n: 3 }, { text: "Activated", tag: "th", n: 4 },
    { sel: "#changelist-form .select2-container", n: 5 },
  ]);

  // student form (Nusrat, roll 81003)
  const href = await js(adminWin, `[...document.querySelectorAll('#result_list a')].find((a) => a.textContent.trim() === '81003').getAttribute('href')`);
  await go(adminWin, href);
  await snap(adminWin, "admin", "04-student-form", [
    { sel: "input[name=roll_number]", n: 1 }, { sel: "input[name=batch]", n: 2 }, { sel: "input[name=correct_batch]", n: 3 },
    { sel: "input[name=is_active]", n: 4 }, { sel: "input[name=new_password]", n: 5 },
  ], { fullPage: true, maxHeight: 1500 });

  // run "Generate first-time passwords" for two students, with the action visible first
  await go(adminWin, "/admin/proctoring/student/");
  await js(adminWin, `(() => {
    const rows = [...document.querySelectorAll('#result_list tbody tr')];
    for (const tr of rows) { const roll = tr.querySelector('th a, td a')?.textContent.trim(); if (['81012', '82003'].includes(roll)) tr.querySelector('input[name=_selected_action]').click(); }
    const select = document.querySelector('select[name=action]'); select.value = 'generate_passwords';
    if (window.django && django.jQuery) django.jQuery(select).val('generate_passwords').trigger('change'); else if (window.jQuery) jQuery(select).val('generate_passwords').trigger('change');
    select.dispatchEvent(new Event('change', { bubbles: true }));
  })()`);
  await sleep(300);
  await snap(adminWin, "admin", "05-student-action", [
    { sel: "#changelist-form .select2-container", n: 1 }, { sel: "#result_list tbody tr:has(input:checked)", n: 2, pad: 2 },
  ]);
  const sheetHtml = await js(adminWin, `(async () => {
    const ids = [...document.querySelectorAll('input[name=_selected_action]:checked')].map((c) => c.value);
    const body = new URLSearchParams(); body.append('action', 'generate_passwords'); ids.forEach((i) => body.append('_selected_action', i));
    body.append('csrfmiddlewaretoken', document.querySelector('input[name=csrfmiddlewaretoken]').value);
    const r = await fetch('/admin/proctoring/student/', { method: 'POST', body, headers: { 'Content-Type': 'application/x-www-form-urlencoded' } });
    return await r.text();
  })()`);
  await adminWin.webContents.executeJavaScript(`document.open(); document.write(${JSON.stringify(sheetHtml)}); document.close();`);
  await sleep(400);
  await snap(adminWin, "admin", "06-password-sheet", [
    { sel: ".warn", n: 1 }, { text: "Print", tag: "button", n: 2 }, { text: "Download CSV", tag: "button", n: 3 }, { sel: "#sheet code", n: 4 },
  ], { fullPage: true, maxHeight: 900 });

  await go(adminWin, "/admin/proctoring/exam/add/");
  await snap(adminWin, "admin", "07-exam-form", [
    { sel: "input[name=exam_id]", n: 1 }, { sel: "input[name=batch]", n: 2 }, { sel: "input[name=form_url]", n: 3 },
    { sel: "input[name=written_enabled]", n: 4, pad: 8 }, { sel: "input[name=practical_enabled]", n: 5, pad: 8 }, { sel: "textarea[name=practical_instructions]", n: 6 },
  ], { fullPage: true, maxHeight: 1800 });

  const physicsHref = await (async () => { await go(adminWin, "/admin/proctoring/exam/"); return js(adminWin, `[...document.querySelectorAll('#result_list a')].find((a) => a.textContent.trim() === 'physics-mid').getAttribute('href')`); })();
  await go(adminWin, physicsHref);
  await js(adminWin, `document.querySelector('[name=teachers_old]') && 0`);
  await snap(adminWin, "admin", "08-exam-teachers", [
    { sel: "#id_teachers", n: 1 }, { sel: "input[name=starts_at_0]", n: 2 }, { sel: "input[name=ends_at_0]", n: 3 },
    { sel: "input[name=webcam_enabled]", n: 4, pad: 8 }, { sel: "input[name=monitoring_enabled]", n: 5, pad: 8 },
  ], { fullPage: true, maxHeight: 3200 });

  await go(adminWin, "/admin/proctoring/exam/");
  await snap(adminWin, "admin", "09-exams-list", [
    { text: "Add exam", tag: "a", n: 1 }, { text: "Archived", tag: "*", n: 2 }, { sel: "#changelist-form .select2-container", n: 3 },
    { text: "Batch", tag: "th", n: 4 }, { text: "Status", tag: "th", n: 5 },
  ]);

  await go(adminWin, "/admin/proctoring/examattempt/");
  await snap(adminWin, "admin", "10-attempts", [
    { sel: "#changelist-form .select2-container", n: 1 }, { text: "Stage", tag: "th", n: 2 }, { text: "Status", tag: "th", n: 3 }, { text: "Last seen", tag: "th", n: 4 },
  ], { fullPage: true, maxHeight: 1300 });

  await go(adminWin, "/admin/proctoring/studenttoken/");
  await snap(adminWin, "admin", "11-sessions", [{ text: "Last seen", tag: "th", n: 1 }, { text: "Expires", tag: "th", n: 2 }]);

  await go(adminWin, "/admin/proctoring/auditentry/");
  await snap(adminWin, "admin", "12-audit", [{ text: "Action", tag: "th", n: 1 }, { text: "Performed by", tag: "th", n: 2 }]);

  await go(adminWin, "/admin/auth/user/");
  await snap(adminWin, "admin", "13-users", [{ sel: "#result_list tbody tr:nth-child(2)", n: 1 }, { text: "Add user", tag: "a", n: 2 }]);

  await go(adminWin, "/admin/proctoring/exam/");
  await js(adminWin, `(() => { const select = document.querySelector('select[name=action]'); select.value = 'archive_selected'; if (window.django && django.jQuery) django.jQuery(select).val('archive_selected').trigger('change'); })()`);
  await snap(adminWin, "admin", "14-exam-actions", [{ sel: "#changelist-form .select2-container", n: 1 }]);

  // ---------------------------------------------------------------- TEACHER
  const tWin = makeWindow(1280, 800, { webPreferences: { partition: "demo-teacher" } });
  await go(tWin, "/teacher/login/");
  await snap(tWin, "teacher", "01-login", [{ sel: "input[name=username]", n: 1 }, { sel: "input[name=password]", n: 2 }, { sel: "button[type=submit]", n: 3 }]);
  await login(tWin, "/teacher/login/", "rahman", "Rahman-demo-1");

  await go(tWin, "/teacher/");
  await snap(tWin, "teacher", "02-exams", [
    { text: "Batch 81", tag: "h2", n: 1 }, { sel: ".exam-card", n: 2 }, { text: "Show", tag: "a", n: 3 }, { text: "Log out", tag: "button", n: 4 },
  ]);

  await go(tWin, "/teacher/exams/physics-mid/", 1500);
  await snap(tWin, "teacher", "03-monitor", [
    { sel: ".tiles", n: 1 }, { sel: "#chips", n: 2 }, { sel: "#search", n: 3 }, { text: "Exam settings", tag: "a", n: 4 },
    { text: "State", tag: "th", n: 5 }, { sel: "#rows tr:nth-child(1) .actions", n: 6 },
  ], { fullPage: true, maxHeight: 1500 });

  await go(tWin, "/teacher/exams/physics-mid/students/81002/");
  await snap(tWin, "teacher", "04-timeline-flagged", [
    { sel: ".tiles .tile:nth-child(1)", n: 1 }, { sel: ".timeline li:nth-child(1)", n: 2 }, { sel: ".timeline img", n: 3 },
  ], { fullPage: true, maxHeight: 1700 });

  await go(tWin, "/teacher/exams/physics-mid/students/81001/");
  await snap(tWin, "teacher", "05-timeline-practical", [{ sel: ".tiles", n: 1 }, { sel: ".timeline img", n: 2 }], { fullPage: true, maxHeight: 1700 });

  await go(tWin, "/teacher/exams/physics-mid/settings/");
  await snap(tWin, "teacher", "06-settings", [
    { sel: "input[name=written_enabled]", n: 1, pad: 8 }, { sel: "input[name=practical_enabled]", n: 2, pad: 8 }, { sel: "textarea[name=practical_instructions]", n: 3 },
    { sel: "input[name=starts_at]", n: 4 }, { sel: "input[name=monitoring_enabled]", n: 5, pad: 8 }, { sel: "input[name=webcam_enabled]", n: 6, pad: 8 },
  ], { fullPage: true, maxHeight: 1900 });

  await go(tWin, "/teacher/exams/physics-mid/students/");
  await snap(tWin, "teacher", "07-students", [{ text: "no password yet", tag: "span", n: 1 }, { text: "New password", tag: "button", n: 2 }, { text: "has password", tag: "span", n: 3 }], { fullPage: true, maxHeight: 1100 });

  // batch first-time passwords sheet (students 81010-81012)
  await go(tWin, "/teacher/exams/physics-mid/");
  const sheet = await js(tWin, `(async () => {
    const token = document.querySelector('input[name=csrfmiddlewaretoken]').value;
    const r = await fetch('/teacher/exams/physics-mid/passwords/', { method: 'POST', headers: { 'X-CSRFToken': token } });
    return await r.text();
  })()`);
  await tWin.webContents.executeJavaScript(`document.open(); document.write(${JSON.stringify(sheet)}); document.close();`);
  await sleep(400);
  await snap(tWin, "teacher", "08-password-sheet", [{ sel: ".warn", n: 1 }, { sel: "#sheet", n: 2 }], { fullPage: true, maxHeight: 900 });

  await go(tWin, "/teacher/exams/math-quiz/marks/");
  await snap(tWin, "teacher", "09-marks-upload", [
    { sel: "input[type=file]", n: 1 }, { sel: "input[name=roll_column]", n: 2 }, { text: "Preview", tag: "button", n: 3 }, { text: "Download marks CSV", tag: "button", n: 4 },
  ], { fullPage: true, maxHeight: 900 });
  const csv = require("fs").readFileSync(path.join(__dirname, "sample", "form-responses.csv"), "utf8");
  const result = await js(tWin, `(async () => {
    const fd = new FormData(); fd.append('responses', new Blob([${JSON.stringify(csv)}], { type: 'text/csv' }), 'responses.csv');
    fd.append('csrfmiddlewaretoken', document.querySelector('input[name=csrfmiddlewaretoken]').value);
    const r = await fetch('/teacher/exams/math-quiz/marks/', { method: 'POST', body: fd });
    return await r.text();
  })()`);
  await tWin.webContents.executeJavaScript(`document.open(); document.write(${JSON.stringify(result)}); document.close();`);
  await sleep(500);
  await snap(tWin, "teacher", "10-marks-result", [
    { text: "Columns used", tag: "p", n: 1 }, { text: "Final mark", tag: "th", n: 2 }, { text: "Note", tag: "th", n: 3 }, { text: "Submitted outside", tag: "h2", n: 4 },
  ], { fullPage: true, maxHeight: 1700 });

  await go(tWin, "/teacher/exams/math-quiz/", 1200);
  await snap(tWin, "teacher", "11-after-exam", [
    { text: "Summary CSV", tag: "a", n: 1 }, { text: "Archive exam", tag: "button", n: 2 }, { text: "Delete screenshots", tag: "a", n: 3 }, { text: "Marks from Google Form", tag: "a", n: 4 },
  ], { fullPage: true, maxHeight: 1100 });

  await go(tWin, "/teacher/exams/math-quiz/delete-evidence/");
  await snap(tWin, "teacher", "12-delete-evidence", [{ sel: "#confirm", n: 1 }, { text: "Delete", tag: "button", n: 2 }], { fullPage: true, maxHeight: 800 });

  await go(tWin, "/teacher/?archived=1");
  await snap(tWin, "teacher", "13-archived", [{ text: "Archived", tag: "h2", n: 1 }, { text: "Hide archived", tag: "a", n: 2 }], { fullPage: true, maxHeight: 1100 });

  console.log(missing.length ? "MISSING MARKS:\n" + missing.join("\n") : "all marks placed");
}

app.whenReady().then(async () => {
  try { await main(); } catch (err) { console.error("CAPTURE FAILED", err); process.exitCode = 1; }
  app.quit();
});
