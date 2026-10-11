const fs = require("fs");
const path = require("path");

for (const dir of ["renderer", "camera", "practical"]) {
  const src = path.join(__dirname, "..", "src", dir);
  const dest = path.join(__dirname, "..", "build", dir);
  fs.mkdirSync(dest, { recursive: true });
  for (const file of fs.readdirSync(src)) {
    if (file.endsWith(".html") || file.endsWith(".css")) {
      fs.copyFileSync(path.join(src, file), path.join(dest, file));
    }
  }
}
