// Run: npx electron scripts/verify-compression.js
// Renders a realistic text-heavy page (like a Google Form), captures it, and compares the old
// full-size PNG with the JPEG settings used for screenshots now.
const { app, BrowserWindow, nativeImage } = require("electron");
const { SCREENSHOT_JPEG_QUALITY, SCREENSHOT_MAX_WIDTH } = require("../build/main/config.js");
const { fitWithin } = require("../build/main/imageSize.js");

const lorem = "Question: Explain how a hash map handles collisions and compare chaining with open addressing, giving the average and worst case complexity of lookups. ";
const html = `<body style="margin:0;font:16px Arial;background:#f0ebf8"><div style="width:770px;margin:24px auto">${
  Array.from({ length: 9 }, (_, i) => `<div style="background:#fff;border:1px solid #dadce0;border-radius:8px;padding:20px;margin-bottom:12px">
    <div style="font-size:18px;margin-bottom:12px">${i + 1}. ${lorem}${lorem}</div>
    ${["A", "B", "C", "D"].map((c) => `<div style="margin:6px 0"><span style="display:inline-block;width:14px;height:14px;border:2px solid #5f6368;border-radius:50%;margin-right:10px"></span>Option ${c}: ${lorem.slice(0, 60)}</div>`).join("")}
  </div>`).join("")}</div></body>`;

app.whenReady().then(async () => {
  const win = new BrowserWindow({ show: false, width: 1920, height: 1080, webPreferences: { offscreen: false } });
  await win.loadURL("data:text/html;charset=utf-8," + encodeURIComponent(html));
  await new Promise((r) => setTimeout(r, 500));
  const full = await win.webContents.capturePage();
  const { width, height } = full.getSize();
  const size = fitWithin(width, height, SCREENSHOT_MAX_WIDTH);
  const png = full.toPNG().length;
  const jpg = full.resize(size).toJPEG(SCREENSHOT_JPEG_QUALITY).length;
  console.log("RESULT", JSON.stringify({ captured: `${width}x${height}`, oldPngKB: Math.round(png / 1024), newJpegKB: Math.round(jpg / 1024), newSize: `${size.width}x${size.height}`, smallerBy: `${(png / jpg).toFixed(1)}x` }));
  app.quit();
});
