// Run: cd desktop && npx electron ../manuals/src/build.js [admin|teacher|student ...]
// Turns manuals/src/content/<role>.js into manuals/<role>-manual.pdf (A4, screenshots, numbered call-outs).
const { app, BrowserWindow } = require("electron");
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const BUILD = path.join(__dirname, ".build");
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const CSS = `
@page { size: A4; margin: 15mm 0 17mm; }
@page cover { size: A4; margin: 0; }
* { box-sizing: border-box; }
body { margin: 0; font: 10.5pt/1.55 -apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif; color: #17302d; }
:root { --brand: #0d9488; --dark: #0f4f49; --soft: #e8f4f1; --line: #d3e3df; --muted: #5b7370; --mark: #ea580c; }
.cover { page: cover; height: 297mm; padding: 38mm 24mm 24mm; background: linear-gradient(160deg, #f0faf8 0%, #e1f1ed 100%); page-break-after: always; position: relative; }
.cover img.logo { width: 34mm; height: 34mm; border-radius: 8mm; }
.cover h1 { font-size: 34pt; line-height: 1.1; margin: 16mm 0 4mm; color: var(--dark); letter-spacing: -0.5pt; }
.cover .sub { font-size: 15pt; color: var(--brand); margin: 0 0 16mm; }
.cover .aud { font-size: 11pt; max-width: 120mm; color: var(--muted); }
.cover .meta { position: absolute; left: 24mm; bottom: 22mm; color: var(--muted); font-size: 10pt; }
.page { padding: 20mm 20mm 18mm; }
.body { padding: 4mm 20mm 6mm; }
.toc { page-break-after: always; padding-top: 6mm; }
.toc h2 { font-size: 20pt; color: var(--dark); margin: 0 0 8mm; }
.toc ol { list-style: none; padding: 0; margin: 0; counter-reset: s; }
.toc li { padding: 3.2mm 0; border-bottom: 1px solid var(--line); font-size: 11.5pt; display: flex; gap: 5mm; }
.toc li b { color: var(--brand); min-width: 8mm; }
.toc .intro { color: var(--muted); margin-bottom: 8mm; }
section.sec { margin-top: 12mm; }
section.sec:first-of-type { margin-top: 0; }
section.sec .page { padding-top: 0; padding-bottom: 0; }
h2.sec-title { break-after: avoid; font-size: 21pt; color: var(--dark); margin: 0 0 5mm; padding-bottom: 3mm; border-bottom: 3px solid var(--brand); }
h2.sec-title span { color: var(--brand); margin-right: 3mm; }
h3 { font-size: 13.5pt; color: var(--dark); margin: 7mm 0 2mm; break-after: avoid; }
p { margin: 0 0 3mm; } ul, ol { margin: 0 0 4mm; padding-left: 6mm; } li { margin-bottom: 1.4mm; }
code, .kbd { font: 9.5pt Menlo, Consolas, monospace; background: var(--soft); border: 1px solid var(--line); border-radius: 3px; padding: 0 3px; }
pre { font: 9pt/1.5 Menlo, Consolas, monospace; background: #12302d; color: #e6f4f1; border-radius: 6px; padding: 3mm 4mm; margin: 0 0 4mm; white-space: pre-wrap; break-inside: avoid; }
figure { margin: 4mm 0 5mm; break-inside: avoid; }
figure img { width: 100%; border: 1px solid var(--line); border-radius: 6px; display: block; }
figure.narrow img { width: 62%; margin: 0 auto; } figure.small img { width: 46%; margin: 0 auto; } figure.pair { display: flex; gap: 4mm; } figure.pair img { width: 50%; }
.crop { position: relative; width: 100%; overflow: hidden; border: 1px solid var(--line); border-radius: 6px; }
.crop img { position: absolute; left: 0; top: 0; width: 100%; border: 0; border-radius: 0; }
figure.side { display: flex; gap: 6mm; align-items: flex-start; } figure.side .imgcol { width: 78mm; flex: none; } figure.side ol.legend { flex: 1; margin-top: 0; font-size: 10.3pt; }
figcaption { font-size: 9.2pt; color: var(--muted); margin-top: 1.8mm; text-align: center; }
ol.legend { list-style: none; padding: 0; margin: 2.5mm 0 0; counter-reset: l; columns: 1; }
ol.legend li span { flex: 1; }
ol.legend li { counter-increment: l; display: flex; gap: 3mm; align-items: flex-start; font-size: 10pt; margin-bottom: 1.6mm; }
ol.legend li::before { content: counter(l); flex: none; width: 5.2mm; height: 5.2mm; border-radius: 50%; background: var(--mark); color: #fff; font: 700 8.5pt/5.2mm sans-serif; text-align: center; margin-top: 0.4mm; }
.note { border-left: 4px solid var(--brand); background: var(--soft); border-radius: 0 6px 6px 0; padding: 2.5mm 4mm; margin: 3mm 0 4mm; break-inside: avoid; }
.note.warn { border-color: #d97706; background: #fdf5e6; } .note.danger { border-color: #dc2626; background: #fdecec; }
.note b.t { display: block; margin-bottom: 0.5mm; }
table { width: 100%; border-collapse: collapse; margin: 2mm 0 5mm; font-size: 9.6pt; break-inside: auto; }
th { background: var(--dark); color: #fff; text-align: left; padding: 2mm 3mm; font-weight: 600; }
td { padding: 2mm 3mm; border-bottom: 1px solid var(--line); vertical-align: top; } tr { break-inside: avoid; } tr:nth-child(even) td { background: #f6faf9; }
.steps { counter-reset: st; list-style: none; padding: 0; } .steps > li { counter-increment: st; position: relative; padding-left: 9mm; margin-bottom: 2.6mm; }
.steps > li::before { content: counter(st); position: absolute; left: 0; top: 0; width: 6mm; height: 6mm; border-radius: 50%; background: var(--brand); color: #fff; font: 700 9pt/6mm sans-serif; text-align: center; }
.diagram { display: flex; align-items: center; justify-content: center; gap: 4mm; margin: 5mm 0; break-inside: avoid; }
.box { border: 2px solid var(--brand); border-radius: 8px; padding: 4mm 5mm; text-align: center; background: #fff; min-width: 38mm; font-size: 9.5pt; } .box b { display: block; color: var(--dark); font-size: 11pt; }
.arrow { color: var(--brand); font-size: 18pt; } .box.mid { background: var(--soft); }
.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 5mm; } .cols > div { border: 1px solid var(--line); border-radius: 8px; padding: 3mm 4mm; } .cols h4 { margin: 0 0 2mm; color: var(--dark); }
.pairgrid { display: grid; grid-template-columns: 1fr 1fr; gap: 4mm; } .pairgrid figure { margin: 0 0 3mm; } .pairgrid img { width: 100%; }
.bn { font-size: 10.5pt; line-height: 1.7; }
`;

function block(b) {
  if (b.h) return `<h3>${b.h}</h3>`;
  if (b.p) return `<p>${b.p}</p>`;
  if (b.ul) return `<ul>${b.ul.map((x) => `<li>${x}</li>`).join("")}</ul>`;
  if (b.ol) return `<ol class="steps">${b.ol.map((x) => `<li>${x}</li>`).join("")}</ol>`;
  if (b.code) return `<pre>${esc(b.code)}</pre>`;
  if (b.note) return `<div class="note ${b.kind || ""}"><b class="t">${b.title || (b.kind === "warn" ? "Careful" : b.kind === "danger" ? "Important" : "Tip")}</b>${b.note}</div>`;
  if (b.table) return `<table><thead><tr>${b.table.head.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${b.table.rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  if (b.img) {
    const file = path.join(ROOT, "images", b.img);
    if (!fs.existsSync(file)) throw new Error(`Missing image: ${b.img}`);
    const png = fs.readFileSync(file);
    const [w, h] = [png.readUInt32BE(16), png.readUInt32BE(20)];
    let image = `<img src="file://${file}">`;
    if (b.crop || b.cropPx) { // show only a horizontal slice of a tall screenshot so it stays readable at page width
      const [from, to] = b.cropPx ? [b.cropPx[0] / h, b.cropPx[1] / h] : b.crop;
      image = `<div class="crop" style="padding-top:${(((to - from) * h) / w * 100).toFixed(3)}%"><img src="file://${file}" style="margin-top:-${(((from * h) / w) * 100).toFixed(3)}%"></div>`;
    }
    const caption = b.caption ? `<figcaption>${b.caption}</figcaption>` : "";
    const legend = b.legend ? `<ol class="legend" style="counter-reset: l ${(b.legendStart || 1) - 1}">${b.legend.map((l) => `<li><span>${l}</span></li>`).join("")}</ol>` : "";
    if (b.size === "side") return `<figure class="side"><div class="imgcol">${image}${caption}</div>${legend}</figure>`;
    return `<figure class="${b.size || ""}">${image}${caption}${legend}</figure>`;
  }
  if (b.pair) return `<div class="pairgrid">${b.pair.map(block).join("")}</div>`;
  if (b.diagram) return `<div class="diagram">${b.diagram.map((d, i) => (d === "->" ? `<span class="arrow">&harr;</span>` : `<div class="box ${d.mid ? "mid" : ""}"><b>${d.title}</b>${d.text}</div>`)).join("")}</div>`;
  if (b.cols) return `<div class="cols">${b.cols.map((c) => `<div><h4>${c.title}</h4>${c.html}</div>`).join("")}</div>`;
  if (b.html) return b.html;
  throw new Error("Unknown block: " + JSON.stringify(b).slice(0, 80));
}

function render(doc) {
  const logo = "file://" + path.join(ROOT, "..", "desktop", "assets", "admin-logo.png");
  const sections = `<div class="body">` + doc.sections.map((s, i) => `<section class="sec"${s.newPage ? ' style="break-before:page"' : ""}><h2 class="sec-title"><span>${i + 1}</span>${s.title}</h2>${s.blocks.map(block).join("\n")}</section>`).join("\n") + `</div>`;
  return `<!doctype html><html><head><meta charset="utf-8"><title>${esc(doc.title)}</title><style>${CSS}</style></head><body>
<div class="cover"><img class="logo" src="${logo}"><h1>${doc.title}</h1><p class="sub">${doc.subtitle}</p><p class="aud">${doc.audience}</p><div class="meta">ExamProctor · ${esc(doc.version)}<br>${esc(doc.date)}</div></div>
<div class="page toc"><h2>Contents</h2><p class="intro">${doc.intro}</p><ol>${doc.sections.map((s, i) => `<li><b>${i + 1}</b><span>${s.title}</span></li>`).join("")}</ol></div>
${sections}</body></html>`;
}

let win;
async function buildOne(role) {
  const doc = require(path.join(__dirname, "content", `${role}.js`));
  fs.mkdirSync(BUILD, { recursive: true });
  const html = path.join(BUILD, `${role}.html`);
  fs.writeFileSync(html, render(doc));
  win = win || new BrowserWindow({ show: false, width: 900, height: 1200 }); // one window for all manuals (a second window fails to load)
  await win.loadFile(html);
  await new Promise((r) => setTimeout(r, 900));
  const footer = `<div style="font:8px Helvetica,Arial,sans-serif;width:100%;text-align:center;color:#5b7370">ExamProctor · ${doc.footer} · page <span class="pageNumber"></span> of <span class="totalPages"></span></div>`;
  const pdf = await win.webContents.printToPDF({
    pageSize: "A4", printBackground: true, displayHeaderFooter: true, headerTemplate: "<span></span>", footerTemplate: footer,
    preferCSSPageSize: true, generateDocumentOutline: true, generateTaggedPDF: true,
  });
  const out = path.join(ROOT, `${role}-manual.pdf`);
  fs.writeFileSync(out, pdf);
  console.log("saved", path.relative(ROOT, out), `${(pdf.length / 1024 / 1024).toFixed(1)} MB`);
}

app.whenReady().then(async () => {
  const roles = process.argv.filter((a) => ["admin", "teacher", "student"].includes(a));
  try { for (const r of roles.length ? roles : ["admin", "teacher", "student"]) await buildOne(r); } catch (e) { console.error("BUILD FAILED", e); process.exitCode = 1; }
  app.quit();
});
