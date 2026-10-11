// Run: npx electron scripts/verify-content-protection.js
// Opens a bright window, captures the screen with desktopCapturer and with the OS screenshot tool,
// and reports whether the window is visible in each capture (with protection off and on).
const { app, BrowserWindow, desktopCapturer, screen, nativeImage } = require("electron");
const { execFile } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const isRed = (r, g, b) => r > 200 && g < 60 && b < 60;

async function sampleDesktopCapturer(win) {
  const display = screen.getDisplayMatching(win.getBounds());
  const size = { width: display.size.width * display.scaleFactor, height: display.size.height * display.scaleFactor };
  const [source] = await desktopCapturer.getSources({ types: ["screen"], thumbnailSize: size });
  return pixelAt(source.thumbnail, win, display);
}

function pixelAt(image, win, display) {
  const b = win.getBounds();
  const x = Math.round((b.x - display.bounds.x + b.width / 2) * display.scaleFactor);
  const y = Math.round((b.y - display.bounds.y + b.height / 2) * display.scaleFactor);
  const { width } = image.getSize();
  const bmp = image.toBitmap();
  const i = (y * width + x) * 4;
  return [bmp[i + 2], bmp[i + 1], bmp[i]]; // BGRA -> RGB
}

function osScreenshot(win) {
  return new Promise((resolve) => {
    const file = path.join(os.tmpdir(), `cp-${Date.now()}.png`);
    execFile("screencapture", ["-x", file], (err) => {
      if (err || !fs.existsSync(file)) return resolve(null);
      const image = nativeImage.createFromPath(file);
      fs.unlinkSync(file);
      const display = screen.getDisplayMatching(win.getBounds());
      // screencapture output is in physical pixels of the main display
      resolve(pixelAt(image, win, display));
    });
  });
}

app.whenReady().then(async () => {
  const results = {};
  for (const protectedMode of [false, true]) {
    const win = new BrowserWindow({ x: 200, y: 200, width: 400, height: 300, show: true, frame: false, backgroundColor: "#ff0000" });
    await win.loadURL("data:text/html,<body style='margin:0;background:#ff0000'></body>");
    win.setContentProtection(protectedMode);
    win.show();
    await sleep(1500);
    const dc = await sampleDesktopCapturer(win);
    const sc = await osScreenshot(win);
    results[protectedMode ? "protected" : "unprotected"] = {
      desktopCapturer: { rgb: dc, windowVisible: isRed(...dc) },
      screencapture: sc ? { rgb: sc, windowVisible: isRed(...sc) } : "unavailable (no permission?)",
    };
    win.destroy();
  }
  console.log("RESULT", JSON.stringify(results));
  app.quit();
});
