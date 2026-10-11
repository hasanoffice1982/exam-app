// Shared helpers for the screenshot scripts (run inside Electron): capture, annotate, wait.
const { BrowserWindow } = require("electron");
const fs = require("fs");
const path = require("path");

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function makeWindow(width = 1180, height = 780, extra = {}) {
  return new BrowserWindow({ show: false, width, height, useContentSize: true, backgroundColor: "#ffffff", ...extra });
}

/** Saves a PNG of the window (or its whole page when fullPage). Images are scaled to `outWidth` px wide. */
/** Removes the empty band under the last piece of content (the left `ignoreLeft` px, e.g. a sidebar, is ignored). */
function trimBottom(image, { ignoreLeft = 0, pad = 28, tolerance = 6 } = {}) {
  const { width, height } = image.getSize();
  const bmp = image.toBitmap();
  const px = (x, y) => (y * width + x) * 4;
  const scale = width / 1180;
  const bgX = Math.round(ignoreLeft) + Math.round(70 * scale); // the page background just right of any sidebar
  const bg = [bmp[px(bgX, height - 1)], bmp[px(bgX, height - 1) + 1], bmp[px(bgX, height - 1) + 2]];
  const blank = (y) => {
    for (let x = Math.round(ignoreLeft); x < width - Math.round(28 * scale); x += 2) { // skip the scrollbar
      const i = px(x, y);
      if (Math.abs(bmp[i] - bg[0]) > tolerance || Math.abs(bmp[i + 1] - bg[1]) > tolerance || Math.abs(bmp[i + 2] - bg[2]) > tolerance) return false;
    }
    return true;
  };
  let last = height - 1;
  while (last > 0 && blank(last)) last--;
  const keep = Math.min(height, last + 1 + Math.round(pad * (width / 1180)));
  return keep < height - 8 ? image.crop({ x: 0, y: 0, width, height: keep }) : image;
}

async function shot(win, file, { fullPage = false, maxHeight = 1700, outWidth = 1400, settle = 350, trim = true, ignoreLeft = 0 } = {}) {
  const wc = win.webContents;
  const [width] = win.getContentSize();
  let restore;
  if (fullPage) {
    const height = await wc.executeJavaScript("Math.max(document.documentElement.scrollHeight, document.body.scrollHeight)");
    const [, current] = win.getContentSize();
    win.setContentSize(width, Math.min(height, maxHeight));
    restore = () => win.setContentSize(width, current);
    await sleep(settle);
  }
  await sleep(settle);
  let image = await wc.capturePage();
  if (trim) image = trimBottom(image, { ignoreLeft: ignoreLeft * (image.getSize().width / width) });
  const size = image.getSize();
  const scaled = size.width > outWidth ? image.resize({ width: outWidth, quality: "best" }) : image;
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, scaled.toPNG());
  if (restore) restore();
  return file;
}

/**
 * Draws numbered call-outs over page elements. marks: [{ sel | text(+tag), n, pad, side }].
 * `sel` is a CSS selector; `text` matches the first element of `tag` (default *) whose own text contains it.
 */
async function annotate(win, marks) {
  await win.webContents.executeJavaScript(`(${injectMarks.toString()})(${JSON.stringify(marks)})`);
  await sleep(120);
}

async function clearMarks(win) {
  await win.webContents.executeJavaScript(`document.querySelectorAll('[data-mark]').forEach((e) => e.remove())`);
}

function injectMarks(marks) {
  document.querySelectorAll("[data-mark]").forEach((e) => e.remove());
  const found = [];
  for (const m of marks) {
    let el = null;
    if (m.sel) el = document.querySelector(m.sel);
    else if (m.text) {
      const wanted = m.text.toLowerCase();
      el = [...document.querySelectorAll(m.tag || "*")].find((e) => e.children.length < 4 && (e.innerText || "").toLowerCase().trim().startsWith(wanted)) ||
           [...document.querySelectorAll(m.tag || "*")].find((e) => (e.innerText || "").toLowerCase().includes(wanted));
    }
    if (!el) { found.push({ n: m.n, missing: true }); continue; }
    const r = el.getBoundingClientRect();
    const pad = m.pad ?? 4;
    const box = document.createElement("div");
    box.dataset.mark = "box";
    Object.assign(box.style, {
      position: "absolute", left: `${r.left + scrollX - pad}px`, top: `${r.top + scrollY - pad}px`,
      width: `${r.width + pad * 2}px`, height: `${r.height + pad * 2}px`, border: "3px solid #ea580c", borderRadius: "8px",
      pointerEvents: "none", zIndex: 99998, boxSizing: "border-box",
    });
    const badge = document.createElement("div");
    badge.dataset.mark = "badge";
    badge.textContent = String(m.n);
    const side = m.side || "tl";
    const bx = side.includes("r") ? r.right + scrollX + pad - 12 : r.left + scrollX - pad - 12;
    const by = side.includes("b") ? r.bottom + scrollY + pad - 12 : r.top + scrollY - pad - 14;
    Object.assign(badge.style, {
      position: "absolute", left: `${bx}px`, top: `${by}px`, width: "26px", height: "26px", borderRadius: "50%",
      background: "#ea580c", color: "#fff", font: "700 14px/26px -apple-system, Helvetica, Arial", textAlign: "center",
      zIndex: 99999, pointerEvents: "none",
    });
    document.body.append(box, badge);
    found.push({ n: m.n, ok: true });
  }
  return found;
}

module.exports = { sleep, makeWindow, shot, annotate, clearMarks };
