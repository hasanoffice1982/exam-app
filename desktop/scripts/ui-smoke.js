// Run: npx electron scripts/ui-smoke.js   (drives the real renderer with a fake bridge)
const { app, BrowserWindow } = require("electron");
const path = require("path");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

app.whenReady().then(async () => {
  const win = new BrowserWindow({ show: false, width: 600, height: 800, webPreferences: { preload: path.join(__dirname, "ui-smoke-preload.js"), contextIsolation: true, sandbox: false } });
  await win.loadFile(path.join(__dirname, "..", "build", "renderer", "index.html"));
  const js = (code) => win.webContents.executeJavaScript(code);
  const visible = () => js(`[...document.querySelectorAll("section")].filter(s=>!s.hidden).map(s=>s.id)`);
  const text = (id) => js(`document.getElementById("${id}").textContent`);
  const click = (id) => js(`document.getElementById("${id}").click()`);
  const fill = (id, v) => js(`document.getElementById("${id}").value = ${JSON.stringify(v)}`);
  const submit = (id) => js(`document.getElementById("${id}").requestSubmit()`);
  const out = {};

  await click("start-btn"); await sleep(100); out.afterConsent = await visible();
  // wrong login shows the server's message and stays put
  await fill("roll", "42"); await fill("password", "nope"); await submit("login-form"); await sleep(150);
  out.badLogin = { screen: await visible(), error: await text("error") };
  // good login -> exams
  await fill("password", "good-pass"); await submit("login-form"); await sleep(250);
  out.afterLogin = { screen: await visible(), welcome: await text("e-name"), options: await js(`[...document.querySelectorAll("#exam option")].map(o=>o.textContent+(o.disabled?" [disabled]":""))`) };
  // profile
  await click("to-profile"); await sleep(150);
  out.profile = { screen: await visible(), name: await text("pf-name"), roll: await text("pf-roll"), batch: await text("pf-batch"), email: await text("pf-email") };
  // change password: mismatch, wrong current, success
  await fill("pw-current", "good-pass"); await fill("pw-new", "brand-new-1"); await fill("pw-confirm", "different");
  await submit("password-form"); await sleep(100); out.mismatch = await text("error");
  await fill("pw-current", "wrong"); await fill("pw-confirm", "brand-new-1"); await submit("password-form"); await sleep(150); out.wrongCurrent = await text("error");
  await fill("pw-current", "good-pass"); await submit("password-form"); await sleep(150);
  out.changed = { info: await text("info"), errorHidden: await js(`document.getElementById("error").hidden`), fieldsCleared: await js(`document.getElementById("pw-new").value === ""`) };
  // back to exams, then log out
  await click("profile-back"); await sleep(250); out.back = await visible();
  await click("logout-link"); await sleep(150); out.afterLogout = { screen: await visible(), info: await text("info"), passwordCleared: await js(`document.getElementById("password").value===""`) };
  // activation: email is requested, user is sent back to login with a hint
  await click("to-activate"); await fill("a-roll", "7"); await fill("a-email", "ann@x.com"); await submit("activate-form"); await sleep(150);
  out.activation = { screen: await visible(), info: await text("info"), rollPrefilled: await js(`document.getElementById("roll").value`) };
  out.calls = await js(`window.api.__calls()`);
  out.noPasswordScreen = await js(`document.getElementById("password-screen") === null && document.getElementById("gen-pass") === null`);
  console.log("RESULT", JSON.stringify(out));
  app.quit();
});
