// Run: cd desktop && npx electron ../manuals/src/make-sample-images.js
// Draws the sample "evidence" images used by the demo database (clearly illustrative, no real people or brands).
const { app, BrowserWindow } = require("electron");
const fs = require("fs");
const path = require("path");

const out = path.join(__dirname, "sample");

const drawers = `
const W = 1280, H = 720;
function chrome(g, title, accent) {
  g.fillStyle = "#e9edf1"; g.fillRect(0, 0, W, H);
  g.fillStyle = "#ffffff"; g.fillRect(60, 40, W - 120, H - 80);
  g.fillStyle = "#dfe5ea"; g.fillRect(60, 40, W - 120, 44);
  [["#ff5f57", 86], ["#febc2e", 110], ["#28c840", 134]].forEach(([c, x]) => { g.fillStyle = c; g.beginPath(); g.arc(x, 62, 7, 0, 7); g.fill(); });
  g.fillStyle = "#44525c"; g.font = "600 16px Helvetica, Arial"; g.textAlign = "center"; g.fillText(title, W / 2, 68); g.textAlign = "left";
  g.fillStyle = accent; g.fillRect(60, 84, W - 120, 4);
}
function bars(g, x, y, rows, w, color) { for (let i = 0; i < rows; i++) { g.fillStyle = color; g.fillRect(x, y + i * 26, w * (0.55 + ((i * 37) % 45) / 100), 10); } }
const screens = {
  1(g) { chrome(g, "Lab notes.txt", "#0d9488"); g.fillStyle = "#12302d"; g.font = "600 28px Helvetica, Arial"; g.fillText("Circuit 4 - readings", 110, 150);
    g.fillStyle = "#44525c"; g.font = "18px Menlo, monospace"; ["R1 = 220 ohm   V = 4.6 V", "R2 = 470 ohm   V = 7.1 V", "I (measured) = 0.021 A", "I (calculated) = 0.0207 A", "Error: 1.4 %"].forEach((t, i) => g.fillText(t, 110, 200 + i * 34)); bars(g, 110, 400, 7, 900, "#d7dee3"); },
  2(g) { chrome(g, "simulator - circuit4.sim", "#0284c7"); g.fillStyle = "#f6f9fb"; g.fillRect(90, 110, 780, 520);
    g.strokeStyle = "#0284c7"; g.lineWidth = 4; g.strokeRect(190, 210, 520, 300); g.fillStyle = "#0d9488"; g.fillRect(430, 195, 80, 30); g.fillStyle = "#d97706"; g.fillRect(190, 330, 30, 80);
    g.fillStyle = "#12302d"; g.font = "600 20px Helvetica, Arial"; g.fillText("R1", 435, 188); g.fillText("Battery", 110, 380);
    g.fillStyle = "#eef3f6"; g.fillRect(900, 110, 290, 520); g.fillStyle = "#44525c"; g.font = "600 16px Helvetica, Arial"; g.fillText("Components", 920, 140); bars(g, 920, 165, 9, 220, "#cbd5db"); },
  3(g) { chrome(g, "Chat assistant - new chat", "#475569"); g.fillStyle = "#12302d"; g.font = "600 22px Helvetica, Arial"; g.fillText("Chat assistant", 110, 140);
    g.fillStyle = "#eef3f6"; g.fillRect(110, 170, 700, 70); g.fillStyle = "#44525c"; g.font = "17px Helvetica, Arial"; g.fillText("Explain how a hash map handles collisions and compare the options...", 128, 212);
    g.fillStyle = "#eef2f5"; g.fillRect(250, 270, 880, 250); bars(g, 280, 300, 8, 780, "#cbd5db"); g.fillStyle = "#ffffff"; g.fillRect(110, 560, 1020, 56); g.strokeStyle = "#cbd5db"; g.strokeRect(110, 560, 1020, 56); },
  4(g) { chrome(g, "Messages - class group", "#16a34a"); g.fillStyle = "#12302d"; g.font = "600 20px Helvetica, Arial"; g.fillText("Class group", 110, 140);
    [[110, 170, "#e6f4ea", 520], [600, 250, "#dcfce7", 520], [110, 330, "#e6f4ea", 460], [650, 410, "#dcfce7", 470]].forEach(([x, y, c, w]) => { g.fillStyle = c; g.fillRect(x, y, w, 56); bars(g, x + 16, y + 14, 2, w - 60, "#9dc9aa"); }); },
};
const webcams = {
  1(g, W, H) { g.fillStyle = "#cfe3de"; g.fillRect(0, 0, W, H); person(g, W, H, "#d9b99b", "#12302d"); },
  2(g, W, H) { g.fillStyle = "#d6dff0"; g.fillRect(0, 0, W, H); person(g, W, H, "#c99a7b", "#1e3a5f"); },
  3(g, W, H) { g.fillStyle = "#e6dccb"; g.fillRect(0, 0, W, H); person(g, W, H, "#e0b99a", "#5b3a29"); },
};
function person(g, W, H, skin, shirt) {
  g.fillStyle = shirt; g.beginPath(); g.ellipse(W / 2, H + 40, 230, 190, 0, 0, 7); g.fill();
  g.fillStyle = skin; g.beginPath(); g.ellipse(W / 2, H / 2 - 20, 105, 130, 0, 0, 7); g.fill();
  g.fillStyle = "#2a2a2a"; g.beginPath(); g.ellipse(W / 2, H / 2 - 100, 112, 70, 0, Math.PI, 0); g.fill();
  g.fillStyle = "#222"; g.beginPath(); g.arc(W / 2 - 38, H / 2 - 30, 8, 0, 7); g.arc(W / 2 + 38, H / 2 - 30, 8, 0, 7); g.fill();
  g.strokeStyle = "#8a5a44"; g.lineWidth = 5; g.beginPath(); g.arc(W / 2, H / 2 + 20, 40, 0.15 * Math.PI, 0.85 * Math.PI); g.stroke();
}
function render(kind, n) {
  const c = document.getElementById("c");
  if (kind === "screen") { c.width = W; c.height = H; screens[n](c.getContext("2d")); return c.toDataURL("image/png"); }
  c.width = 640; c.height = 480; webcams[n](c.getContext("2d"), 640, 480); return c.toDataURL("image/jpeg", 0.85);
}`;

app.whenReady().then(async () => {
  fs.mkdirSync(out, { recursive: true });
  const win = new BrowserWindow({ show: false });
  await win.loadURL("data:text/html," + encodeURIComponent(`<canvas id=c></canvas><script>${drawers}</script>`));
  const save = (name, url) => fs.writeFileSync(path.join(out, name), Buffer.from(url.split(",")[1], "base64"));
  for (const n of [1, 2, 3, 4]) save(`screen-${n}.png`, await win.webContents.executeJavaScript(`render("screen", ${n})`));
  for (const n of [1, 2, 3]) save(`webcam-${n}.jpg`, await win.webContents.executeJavaScript(`render("webcam", ${n})`));
  console.log("RESULT", fs.readdirSync(out).join(", "));
  app.quit();
});
