#!/usr/bin/env bash
# Rebuilds every screenshot and the three PDF manuals from scratch against a throwaway demo database.
# Usage (from the repo root):  bash manuals/src/run-all.sh
set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEMO=/tmp/examapp-demo
cd "$ROOT/desktop" && npm run build >/dev/null

bash "$ROOT/manuals/src/demo-env.sh" stop >/dev/null || true
bash "$ROOT/manuals/src/demo-env.sh" start

echo "== admin + teacher screenshots"
DEMO_URL=http://127.0.0.1:8780 npx electron ../manuals/src/capture-web.js 2>&1 | grep -E "saved|MISSING|FAILED|mark " || true

echo "== student app screenshots (real app, monitoring off so the demo machine's own apps do not block the start)"
(cd "$ROOT/backend" && DATABASE_PATH="$DEMO/db.sqlite3" MEDIA_ROOT="$DEMO/media" .venv/bin/python manage.py shell -c \
  "from apps.proctoring.models import Exam; Exam.objects.filter(exam_id='physics-mid').update(monitoring_enabled=False)" >/dev/null 2>&1)
for phase in a b; do
  BACKEND_URL=http://127.0.0.1:8780 npx electron ../manuals/src/capture-app.js $phase 2>&1 | grep -E "saved|MISSING|FAILED|did not" || true
done
npx electron ../manuals/src/capture-illustrations.js 2>&1 | grep -E "saved|rror" || true

echo "== PDFs"
npx electron ../manuals/src/build.js 2>&1 | grep -E "saved|FAILED|Error"
bash "$ROOT/manuals/src/demo-env.sh" stop
