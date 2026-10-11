// Run: cd desktop && npx electron ../manuals/src/capture-illustrations.js
// macOS draws the app's pop-up dialogs itself, so they cannot be screenshotted by the app. These images redraw them
// with the exact wording from the code, and compose the installer window. They are labelled "illustration" in the manual.
const { app, BrowserWindow } = require("electron");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { sleep } = require("./lib");

const OUT = path.join(__dirname, "..", "images", "student");
const ICON = "file://" + path.join(__dirname, "..", "..", "desktop", "assets", "icon.png");
const BG = "file://" + path.join(__dirname, "..", "..", "desktop", "assets", "dmg-background@2x.png");

const dialogs = {
  "d01-switched-away": { message: "You switched away from the exam window. Would you like to quit the exam?", detail: "If you quit the exam, you will be marked 0.", buttons: ["Return to exam", "Quit exam"], primary: 0 },
  "d02-written-submitted": { message: "Your written answers were submitted.", detail: "Next comes the practical part. Click the button to start it.", buttons: ["Start practical part"], primary: 0 },
  "d03-finish-practical": { message: "Finish the practical part now?", detail: "Make sure your work is saved and handed in as your teacher instructed. You cannot come back after finishing.", buttons: ["Keep working", "Finish"], primary: 0 },
  "d04-time-up": { message: "Time is up. The exam has ended.", detail: "This window will now close.", buttons: ["OK"], primary: 0 },
  "d05-blocked-app": { message: "Please close OBS Studio.", detail: "Screen sharing, recording and remote-access apps are not allowed during the exam. This has been recorded.", buttons: ["OK"], primary: 0 },
  "d06-session-ended": { message: "Your session has ended.", detail: "You logged in elsewhere or your teacher ended your session. The exam window will close.", buttons: ["OK"], primary: 0 },
};

const dialogHtml = (d) => `<!doctype html><meta charset=utf-8><style>
html,body{overflow:hidden}::-webkit-scrollbar{display:none}
body{margin:0;background:transparent;font:13px/1.4 -apple-system,Helvetica,Arial,sans-serif}
.d{width:420px;box-sizing:border-box;margin:18px;padding:22px 22px 18px;background:#ececec;border:1px solid #c9c9c9;border-radius:14px;color:#1d1d1f}
.top{display:flex;gap:16px}.top img{width:58px;height:58px;flex:none}.m{font-weight:700;font-size:13.5px;margin:2px 0 6px}.x{color:#3c3c3f;font-size:12.5px}
.b{display:flex;justify-content:flex-end;gap:8px;margin-top:18px}.btn{padding:4px 16px;border-radius:6px;border:1px solid #c4c4c4;background:#fff;font-size:13px}
.btn.p{background:#0d9488;border-color:#0d9488;color:#fff}</style>
<div class=d><div class=top><img src="${ICON}"><div><div class=m>${d.message}</div><div class=x>${d.detail}</div></div></div>
<div class=b>${d.buttons.slice().reverse().map((b, i, a) => `<span class="btn${a.length - 1 - i === d.primary ? " p" : ""}">${b}</span>`).join("")}</div></div>`;

const installHtml = `<!doctype html><meta charset=utf-8><style>html,body{overflow:hidden}::-webkit-scrollbar{display:none}
body{margin:0;width:660px;height:400px;position:relative;background:url(${BG}) 0 0/660px 400px;font:13px -apple-system,Helvetica,Arial,sans-serif;color:#1d1d1f}
.i{position:absolute;top:140px;width:120px;text-align:center}.i img{width:100px;height:100px}
.f{width:96px;height:74px;margin:14px auto 12px;background:#5aa9e6;border-radius:8px 8px 6px 6px;position:relative}.f:before{content:"";position:absolute;left:0;top:-10px;width:44px;height:14px;background:#5aa9e6;border-radius:6px 6px 0 0}
.f:after{content:"";position:absolute;left:0;right:0;top:6px;bottom:0;background:#7bbcf0;border-radius:6px}</style>
<div class=i style="left:120px"><img src="${ICON}"><div>ExamProctor</div></div>
<div class=i style="left:420px"><div class=f></div><div>Applications</div></div>`;

let win;
async function render(html, width, height, file) {
  win.setContentSize(width, height);
  // a file:// page (not a data: URL) so it is allowed to show the local icon and background images
  const page = path.join(os.tmpdir(), "illustration.html");
  fs.writeFileSync(page, html);
  await win.loadFile(page);
  await sleep(500);
  fs.writeFileSync(file, (await win.webContents.capturePage()).toPNG());
  console.log("saved", path.relative(path.join(__dirname, ".."), file));
}

app.whenReady().then(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  win = new BrowserWindow({ show: false, width: 700, height: 420, useContentSize: true, transparent: true, frame: false });
  for (const [name, d] of Object.entries(dialogs)) await render(dialogHtml(d), 460, d.detail.length > 90 ? 196 : 176, path.join(OUT, `${name}.png`));
  await render(installHtml, 660, 400, path.join(OUT, "09-install-window.png"));
  app.quit();
});
