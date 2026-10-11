# Exam Proctoring MVP

- `backend/` — Django + DRF API (SQLite), app `apps/proctoring`
- `desktop/` — Electron (TypeScript) student client

## Setup

### Backend
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_exams          # creates math-101, physics-101
python manage.py createsuperuser     # for /admin/
python manage.py runserver 0.0.0.0:8000
```
Replace the dummy `form_url` of the seeded exams with a real Google Form URL in `/admin/` → Exams.

### Desktop
```bash
cd desktop
cp .env.example .env     # set BACKEND_URL (e.g. http://192.168.1.10:8000 on the LAN)
npm install
npm run dev              # or: npm start
```
On macOS, grant the app (Electron / your terminal) **Screen Recording** permission in System Settings → Privacy & Security, otherwise screenshots come out blank/fail.

## Packaging installers (electron-builder)
Set `BACKEND_URL` in `desktop/.env` first: the file is baked into the installer, so students never configure anything.
```bash
cd desktop
npm run build:mac    # dist/*.dmg (universal: Intel + Apple Silicon), builds natively on a Mac
npm run build:win    # dist/*.exe (NSIS, x64); needs Wine: brew install --cask wine-stable
npm run build:all    # both
```
- TypeScript compiles to `desktop/build/`; installers land in `desktop/dist/`.
- Builds are **unsigned** for the MVP. Tell students:
  - macOS Gatekeeper warning: right-click the app → **Open** → Open.
  - Windows SmartScreen warning: **More info** → **Run anyway**.
- On macOS, students must still allow **Screen Recording** for ExamProctor on first run (System Settings → Privacy & Security), then restart the app.

## Students and passwords
Upload students with a CSV (`roll_number,name,email[,batch]`):
```bash
cd backend && python manage.py import_students students.csv
```
First time: the student clicks **First time? Activate account** and enters their roll number and registered email. If they match, the system generates a random 12-character password, stores only its hash and **emails the password to that address**. The password is never shown in the app or returned by the API, so only the owner of the registered inbox can obtain it. The student then logs in with roll number + emailed password.
- If the email cannot be sent the account stays not-activated and the student can retry.
- Forgot the password? In `/admin/` -> Students, select the student -> action **Reset activation**; they activate again and get a new password by email.
- Wrong roll/email combinations are limited to 5 failures per roll number, then a 15-minute lockout; the error is the same for unknown rolls and wrong emails.

### Email setup (Brevo or Resend, via SMTP)
Set these on the server before `runserver`/`gunicorn` (never in the code):
```bash
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp-relay.brevo.com            # Resend: smtp.resend.com
EMAIL_PORT=587
EMAIL_HOST_USER=<Brevo login email>        # Resend: the word  resend
EMAIL_HOST_PASSWORD=<Brevo SMTP key>       # Resend: your API key
DEFAULT_FROM_EMAIL=<a sender you verified>
```
Brevo works with a single verified sender address; Resend needs a verified domain. With the default console backend (development) the email is printed in the server terminal; `EMAIL_BACKEND=django.core.mail.backends.filebased.EmailBackend EMAIL_FILE_PATH=/tmp/mails` writes each email to a file instead. `manage.py check` warns (`proctoring.W001`) if production would still use the console backend.

### Teacher/admin-issued passwords (no email needed)
Handing out passwords yourself works without any email account:
- **Teacher:** on the exam's live monitor, **First-time passwords (batch N)** gives every student of that exam's batch who has no password yet their own random 12-character password. A printable sheet is shown **once** (Print / Download CSV); only hashes are stored. Students who already have a password are never touched, and a teacher can only do this for their own exams.
- **Admin:** in `/admin/` -> Students, select students -> **Generate first-time passwords** (also replaces an existing password and ends that student's session).
- Set `SELF_ACTIVATION=0` on the server to turn off the "First time? Activate account" emailing, so students must get their password from a teacher. Both methods can be used together (default `SELF_ACTIVATION=1`).
- Never use one shared password for a batch: each student gets a different random one.

### Student account screen
After login, the exam list has **My profile** (name, roll, batch, masked email) with **Change password** (current password required, new one at least 8 characters, different from the current one and not the roll number; 5 wrong current passwords lock it for 15 minutes) and **Log out** (revokes the session on the server).

## Teacher dashboard (`/teacher/`)
Log in with your teacher account (same login page as `/admin/`); you only see exams assigned to you.
- **Live monitor** per exam: every student with online/offline state (online = heartbeat within 90 s), flag (clean / review / flagged), score, tab switches and last event. Refreshes every 10 s. Buttons: **End attempt** and **Allow restart**.
- **Student timeline**: events and screenshots merged in time order.
- **CSV export**: per-student summary and the full event log (cells starting with `=`, `+`, `-`, `@` are neutralised against spreadsheet formula injection).
- **Scoring** (`backend/apps/proctoring/scoring.py`): tab switch 1, copy/paste 1, left full screen 2, dev tools 2, extra display 3, screen-share/remote/recording app 3. Score 1-4 = review, 5+ = flagged. Adjust the weights there.
- Screenshots are not served from `/media/`; they are only reachable through access-checked dashboard/admin links.
- Use `/admin/` (superuser) for the back office: students, batches, exams, teacher assignment.

## Batches
Each student has a **batch** number; each exam can be limited to one batch (empty = all batches). Students only see and can only start exams for their batch.
Batches move **forward only** (81 -> 82 or 85, never 95 -> 94; first assignment is free). The rule is enforced in the model, in `/admin/` and in the CSV import (offending rows are skipped and reported). Every move is logged in the student's *Batch changes* table with who did it. Only superusers manage students and batches.

## Teachers (per-subject access)
```bash
cd backend && python manage.py create_teacher mathteacher --exams math-101,physics-101   # prints a one-time password
```
A teacher logs into `/admin/` and only sees the exams assigned to them (also editable by a superuser on the exam page: *Teachers*), plus those exams' attempts, events, screenshots and consents. They can change the exam's schedule, form URL, monitoring toggle and grace time, but not its batch, name or teacher list, and cannot add/delete exams or touch students, sessions or other subjects.

## Attempts, quitting and force-end
Each student gets one **attempt** per exam, created when they begin. Resuming after a crash is fine. Quitting (`exam_quit`) or running out of time (`time_up`) closes it, and the student cannot re-enter.
Teachers manage attempts in `/admin/` -> Exam attempts (with last-seen time):
- **Force end**: revokes the student's session (their window closes within ~30 s), blocks re-entry and logs a `force_ended` event with the teacher's username.
- **Reset**: deletes the attempt so the student can start again (technical problems, mistakes).

## Webcam photos
Per exam in `/admin/` (teachers can edit it on their own exams): **Webcam enabled** and **Webcam interval seconds** (30-3600, default 180, randomised +/-50% so photos can't be predicted).
- When enabled, the exam won't start without a working camera. The first photo, taken at start, is the identity photo.
- The exam window never gets camera access. A separate hidden window opens the camera for about a second per photo, so the camera light is on only briefly. Web pages get no permissions at all.
- A black image (lens covered) or a missing/busy/denied camera mid-exam logs `camera_unavailable` (score 2) with the reason. Photos appear in the student timeline labelled *Webcam photo*.
- macOS asks for Camera permission the first time; allow it for the app. Face detection is not included: teachers review the photos.

## Screenshot size
Screenshots are captured at most 1280 px wide and saved as JPEG (quality 70) instead of full-resolution PNG, so uploads are faster and storage grows slower. Tune it in `desktop/.env` (`SCREENSHOT_MAX_WIDTH`, `SCREENSHOT_JPEG_QUALITY`). Measured on a text-heavy 1920 px page (`npm run verify:compression` in `desktop/`): old PNG 208 KB; 1600 px q70 = 138 KB; **1280 px q70 = 97 KB (default)**; 1024 px q55 = 55 KB. Savings are larger on high-DPI (Retina) screens and photo-like content, where the old full-resolution PNG was several times bigger.

## Content protection
The launcher and exam windows are excluded from screenshots, screen recordings and screen sharing (Electron `setContentProtection`: macOS window sharing off, Windows capture exclusion), so they appear black to capture tools. The exam window follows the exam's monitoring toggle. Limits: a phone camera pointed at the screen cannot be blocked by software. Run `npm run verify:protection` in `desktop/` to test this on a machine (needs Screen Recording permission).

## Marks from Google Form responses
Dashboard -> exam -> **Marks from Google Form responses**: upload the Form's responses CSV. Matching is by roll number (column detected, or typed in). Nothing is stored.
Policy: quit the exam -> 0; ended by teacher -> blank; no form submission -> blank; otherwise the form's own score. Flagged students get a "review first" note, repeated submissions use the latest, and roll numbers that submitted the form without a proctored attempt are listed as *submitted outside the app*. **Download marks CSV** gives the final sheet.

## Crashes, power cuts and extra time
- A crash or power cut is **not** a quit. The student logs in again and resumes the same attempt; each reopening is logged as `exam_resumed` and shown as **Restarts** on the live monitor (it does not add to the proctor score).
- Google Form answers survive only if the Form requires sign-in (Form settings: require sign-in / limit to 1 response): Google then keeps the respondent's progress as a draft and the student sees it again when they reopen the form while signed in. Anonymous forms lose partial answers. The app keeps the Google login between restarts. Test this on a sample form once.
- The clock keeps running while a student is offline. Teachers give lost time back per student with **+10 min** on the live monitor (repeatable, max 480 min per student, logged as `time_extended`). It also reopens a student whose time had just run out; quit or teacher-ended attempts need **Allow restart**. A student's own deadline is returned by the config endpoint (one extra query on timed exams) and picked up within 2 minutes.

## Exam schedule
Set **Starts at / Ends at** per exam in `/admin/` → Exams (empty = unrestricted). Students can only begin exams with status *open*; the exam window warns and closes automatically at the end time (server clock; changes made by the teacher are picked up within 2 minutes).

## Flow
Consent → Login (name, roll, exam from `/api/exams/`) → Exam window (Google Form rendered inside Electron, resizable, not fullscreen).
Consent is timestamped on click and POSTed to `/api/consent/` at login, once the student/exam are known.

## API
All endpoints need `Authorization: Bearer <token>` (issued by login/activate) except login, activate and the admin-key config write. The student identity is taken from the token, never from the request body.

| Method | Path | Notes |
|---|---|---|
| POST | `/api/login/` | `{roll_number, password, website}` -> profile + `token` |
| POST | `/api/auth/activate/` | `{roll_number, email, website}` -> profile + one-time `password` + `token` |
| POST | `/api/heartbeat/` | called every 30 s by the exam window |
| GET | `/api/exams/` | exams for the student's batch: `[{exam_id, name, starts_at, ends_at, status}]` |
| POST | `/api/exams/<exam_id>/start/` | begins/resumes the attempt, returns the config; 403 with a reason if not allowed |
| GET | `/api/config/<exam_id>/` | `{monitoring_enabled, form_url, mode, starts_at, ends_at, grace_seconds, status, server_time}` |
| POST | `/api/config/<exam_id>/` | teacher write, header `X-Admin-Key` |
| POST | `/api/consent/` | `{exam_id, timestamp?}` |
| POST | `/api/events/` | `{exam_id, event_type, timestamp?, client_id?}` |
| POST | `/api/screenshots/` | multipart: `exam_id, file (png/jpeg <=10MB), timestamp?, client_id?` |

Security notes
- One active session per student: a new login revokes the previous token (also revocable in `/admin/` -> Student tokens; the exam window closes at its next heartbeat/poll).
- `client_id` (UUID) makes event/screenshot uploads idempotent: retries return the original row (200) instead of duplicating.
- Rate limits: 20/min per IP on login/activate, 5 failures per roll number -> 15 min lockout, 300/min events, 60/min uploads.
- Honeypot: login/activate carry a hidden `website` field; if anything fills it the request is refused and that IP is blocked for an hour.
- Counters live in Django's cache (LocMem, per process). Use Redis if you run multiple workers.

Toggle monitoring or change times without rebuilding the app (clients re-poll every 2 min). Set a key first: `ADMIN_API_KEY=choose-a-secret python manage.py runserver`, then
```bash
curl -X POST localhost:8000/api/config/math-101/ -H 'X-Admin-Key: choose-a-secret' -H 'Content-Type: application/json' -d '{"monitoring_enabled": false}'
```
(or edit the exam in `/admin/`). `grace_seconds` (default 3): switching away for less than that is ignored.

Offline behaviour: events and screenshots go into a durable on-disk queue and are retried until the server accepts them; `connection_lost` / `connection_restored` events record network gaps.

## Tests
```bash
cd backend && python manage.py test apps.proctoring     # API, auth, throttling, honeypot, idempotency, query counts
cd desktop && npm test                                   # upload queue, grace timer, API client
```

## Anti-cheat (exam window)
Active while the exam's `monitoring_enabled` is on (the teacher toggle switches all of it off):
- Copy/cut/paste, DevTools, view-source/print/save shortcuts and the right-click menu are blocked; question text can't be selected; the clipboard is cleared at start and whenever the window regains focus. Each attempt is logged (`clipboard_attempt`, `devtools_attempt`, `blocked_shortcut`, at most one per 5 s per type).
- Navigation is limited to Google Form/sign-in/asset hosts (and the form's own origin); anything else is refused and logged as `blocked_navigation` with the host.
- The exam will not start with more than one display connected (turn monitoring off for that exam if a lab needs external monitors). A display plugged in mid-exam logs `display_added` and shows a notice. Mirrored displays look like one display to the OS and are not detected.
- The exam will not start while remote-access or screen-recording apps are running (TeamViewer, AnyDesk, Parsec, RustDesk, VNC/Screen Sharing, Chrome Remote Desktop, OBS, ScreenFlow, Camtasia, Bandicam, ShareX, Loom, Snagit, ...). The process list is re-checked every 30 s: new ones log `blocked_app_detected` and show a notice. Zoom, Discord, Teams, Skype, Slack and Webex are only logged (`watch_app_detected`). The list is in `desktop/src/main/processes.ts`.
- All of this is deterrence plus an audit trail, not a sandbox: a determined student can use a second device. Details such as the app name are in the `detail` column of Proctor events in `/admin/`.

## Manual end-to-end test
1. Start backend and desktop app; click **Start Exam**, log in as e.g. `Test User` / `42` / Mathematics 101.
2. Confirm the form loads inside the Electron window.
3. Click another app (or Cmd/Alt+Tab) → within a second or two a `tab_switch` event and a screenshot are created. Switch back → `returned_to_exam`.
4. Check `/admin/`: **Proctor events** (student, exam, type, time), **Proctor screenshots** (thumbnail preview), **Consents**. Files are stored in `backend/media/screenshots/<exam_id>/<student>/`.
5. Toggle test: POST `monitoring_enabled: false` (curl above, or untick it in `/admin/` -> Exams), wait up to 2 min, switch away again → no new rows. Re-enable and repeat.
6. Failures are only logged to the Electron console (terminal running `npm run dev`); nothing is shown to the student.

## Extending
- TODO in `backend/apps/proctoring/views.py`: add auth before exposing beyond a trusted network.
- Swap SQLite → Postgres in `config/settings.py`; swap `MEDIA_ROOT` storage for S3 via `STORAGES`.
- `Exam.mode` (`form` / `practical`) is already exposed in the config endpoint for future exam types.
