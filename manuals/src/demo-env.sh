#!/usr/bin/env bash
# Starts an isolated demo (own database, own media folder, ports 8780/8781) and prints nothing else.
# Usage:  source manuals/src/demo-env.sh start   |   source manuals/src/demo-env.sh stop
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../.." && pwd)"
DEMO=/tmp/examapp-demo
case "$1" in
  start)
    rm -rf "$DEMO"; mkdir -p "$DEMO/media"
    export DATABASE_PATH="$DEMO/db.sqlite3" MEDIA_ROOT="$DEMO/media" DJANGO_DEBUG=1 TIME_ZONE=Asia/Dhaka
    cd "$ROOT/backend"
    .venv/bin/python manage.py migrate -v0
    .venv/bin/python manage.py seed_demo --sample-images "$ROOT/manuals/src/sample" --form-url "http://127.0.0.1:8781/form.html" >/dev/null
    (.venv/bin/python manage.py runserver 127.0.0.1:8780 --noreload >"$DEMO/server.log" 2>&1 &)
    (cd "$ROOT/manuals/src/sample-form" && python3 -m http.server 8781 --bind 127.0.0.1 >"$DEMO/form.log" 2>&1 &)
    for i in $(seq 1 20); do curl -s -o /dev/null http://127.0.0.1:8780/ && break; sleep 0.5; done
    echo "demo server up on http://127.0.0.1:8780"
    ;;
  stop)
    pkill -f "runserver 127.0.0.1:8780" 2>/dev/null || true
    pkill -f "http.server 8781" 2>/dev/null || true
    echo "demo server stopped"
    ;;
esac
