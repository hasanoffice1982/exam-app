// Run: npx electron scripts/make-assets.js
// Draws the app icon and the .dmg installer background into desktop/assets/ (no image tools needed).
const { app, BrowserWindow } = require("electron");
const fs = require("fs");
const path = require("path");

const out = path.join(__dirname, "..", "assets");
const PAGE = `<canvas id=c></canvas>`;

// Each function draws on a 2D context scaled so 1 unit = 1 CSS px of the target design size.
const drawIcon = `(size) => {
  const c = document.getElementById("c"); c.width = c.height = size;
  const g = c.getContext("2d"); const s = size / 1024; g.scale(s, s);
  const inset = 100, w = 824, r = 185;                       // macOS icon grid: 824px squircle inside 1024
  g.beginPath(); g.roundRect(inset, inset, w, w, r);
  const bg = g.createLinearGradient(inset, inset, inset + w, inset + w);
  bg.addColorStop(0, "#0f766e"); bg.addColorStop(1, "#14b8a6");
  g.shadowColor = "rgba(15,23,42,.35)"; g.shadowBlur = 40; g.shadowOffsetY = 18; g.fillStyle = bg; g.fill();
  g.shadowColor = "transparent";
  // shield
  g.beginPath();
  g.moveTo(512, 235); g.bezierCurveTo(600, 285, 680, 300, 735, 300);
  g.lineTo(735, 520); g.bezierCurveTo(735, 650, 640, 735, 512, 790);
  g.bezierCurveTo(384, 735, 289, 650, 289, 520);
  g.lineTo(289, 300); g.bezierCurveTo(344, 300, 424, 285, 512, 235); g.closePath();
  g.fillStyle = "#ffffff"; g.fill();
  // check mark
  g.beginPath(); g.moveTo(405, 510); g.lineTo(486, 590); g.lineTo(630, 430);
  g.lineWidth = 56; g.lineCap = "round"; g.lineJoin = "round"; g.strokeStyle = "#0f766e"; g.stroke();
  return c.toDataURL("image/png");
}`;

// Flat logo for the web admin: no shadow, no transparent margin.
const drawLogo = `(size) => {
  const c = document.getElementById("c"); c.width = c.height = size;
  const g = c.getContext("2d"); const s = size / 1024; g.scale(s, s);
  g.beginPath(); g.roundRect(0, 0, 1024, 1024, 230);
  const bg = g.createLinearGradient(0, 0, 1024, 1024); bg.addColorStop(0, "#0f766e"); bg.addColorStop(1, "#14b8a6");
  g.fillStyle = bg; g.fill();
  g.beginPath();
  g.moveTo(512, 150); g.bezierCurveTo(620, 210, 720, 228, 790, 228);
  g.lineTo(790, 510); g.bezierCurveTo(790, 680, 670, 790, 512, 860);
  g.bezierCurveTo(354, 790, 234, 680, 234, 510);
  g.lineTo(234, 228); g.bezierCurveTo(304, 228, 404, 210, 512, 150); g.closePath();
  g.fillStyle = "#ffffff"; g.fill();
  g.beginPath(); g.moveTo(385, 505); g.lineTo(485, 605); g.lineTo(660, 405);
  g.lineWidth = 70; g.lineCap = "round"; g.lineJoin = "round"; g.strokeStyle = "#0f766e"; g.stroke();
  return c.toDataURL("image/png");
}`;

const drawBackground = `(scale) => {
  const c = document.getElementById("c"); c.width = 660 * scale; c.height = 400 * scale;
  const g = c.getContext("2d"); g.scale(scale, scale);
  const bg = g.createLinearGradient(0, 0, 660, 400); bg.addColorStop(0, "#f0fdfa"); bg.addColorStop(1, "#ecfeff");
  g.fillStyle = bg; g.fillRect(0, 0, 660, 400);
  g.textAlign = "center"; g.fillStyle = "#134e4a"; g.font = "600 22px -apple-system, Helvetica, Arial";
  g.fillText("Install ExamProctor", 330, 58);
  g.fillStyle = "#0f766e"; g.font = "15px -apple-system, Helvetica, Arial";
  g.fillText("Drag the app onto the Applications folder", 330, 84);
  // arrow between the two icons (icons sit at x=180 and x=480, y=200)
  g.strokeStyle = "#2dd4bf"; g.fillStyle = "#2dd4bf"; g.lineWidth = 5; g.lineCap = "round"; g.setLineDash([2, 12]);
  g.beginPath(); g.moveTo(250, 200); g.lineTo(385, 200); g.stroke(); g.setLineDash([]);
  g.beginPath(); g.moveTo(410, 200); g.lineTo(380, 180); g.lineTo(380, 220); g.closePath(); g.fill();
  g.fillStyle = "#64748b"; g.font = "13px -apple-system, Helvetica, Arial";
  g.fillText("First time opening it? macOS may ask for permission: see the install guide.", 330, 352);
  return c.toDataURL("image/png");
}`;

const save = (name, dataUrl) => fs.writeFileSync(path.join(out, name), Buffer.from(dataUrl.split(",")[1], "base64"));

app.whenReady().then(async () => {
  fs.mkdirSync(out, { recursive: true });
  const win = new BrowserWindow({ show: false, webPreferences: { offscreen: false } });
  await win.loadURL("data:text/html," + encodeURIComponent(PAGE));
  const run = (fn, arg) => win.webContents.executeJavaScript(`(${fn})(${arg})`);
  save("icon.png", await run(drawIcon, 1024));
  save("admin-logo.png", await run(drawLogo, 160));
  save("dmg-background.png", await run(drawBackground, 1));
  save("dmg-background@2x.png", await run(drawBackground, 2));
  console.log("RESULT assets written:", fs.readdirSync(out).join(", "));
  app.quit();
});
