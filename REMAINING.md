# Remaining work (saved for later)

Done: archive exam + evidence deletion + retention sweep + deactivate batch (audit log), calmer admin theme fixes, teacher/admin separation (own teacher login, teachers not staff), Jazzmin admin theme, exam settings page for teachers, every exam has exactly one batch, written + practical exam parts (written first, then practical), teacher/admin-issued passwords, change password + profile + logout, email-the-password activation (needs SMTP credentials to go live); phases 1-5 (security, anti-cheat, exam control/batches/teachers, teacher dashboard, webcam + marks), screenshot compression, crash/extra-time handling, student install guide.

## Build status
- `npm run build:mac` works (fixed: `arch` must sit inside each electron-builder target). Output: `desktop/dist/ExamProctor-0.1.0-universal.dmg` (217 MB, Intel + Apple Silicon). The packaged app launches and the user confirmed it works on their Mac (2026-10-11); `.env` is baked in, currently `BACKEND_URL=http://127.0.0.1:8000`, so **change it to the real server address and rebuild before giving the file to students**.
- Windows `.exe`: skipped for now (decision: only `.dmg`).
- Server deployment: to discuss tomorrow.

## Decided to skip for now
- **Code signing** (Apple $99/yr, Windows cert ~$100-400/yr): installers go out unsigned via Google Drive; students use `STUDENT_INSTALL.md`.
- **Auto-update**: not possible via Drive. Alternative below (minimum version check).

## Ideas from the network-outage discussion (not built)
- Show the student a small non-blocking notice when the connection to the server is lost >30 s ("answers stay in the form; reconnect to submit").
- If a student is offline when time runs out, offer a short grace period before closing the window.

## To do
1. **Email delivery: code is DONE** (password is emailed on activation, tested end to end with file-based email). Still needed from the user: an SMTP account (Brevo or Resend) and the env vars from the README on the server. Until then emails print in the server terminal.
2. **Download page** `/download/` that detects Mac/Windows and shows the right Google Drive link (undecided; paste Drive links into a setting).
3. **Minimum client version check**: server setting; an outdated app refuses to start the exam and points to the Drive link (undecided).
4. **Cloud storage (S3)** for screenshots instead of local disk (undecided; needs a bucket and keys).
5. **Backend hosting decision** (also: `collectstatic` + WhiteNoise so the Jazzmin admin styles load with DEBUG off; set `TIME_ZONE`): students need a reachable `BACKEND_URL` baked into the installer (LAN IP, or a tunnel/hosted server if remote). Production setup: HTTPS, gunicorn, Postgres, Redis cache (throttle counters), `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0`, `ADMIN_API_KEY`.
6. **Real-world checks nobody has run yet**:
   - macOS Screen Recording permission, then a real screenshot (`npm run verify:protection` for the black-screen protection).
   - Google Form draft recovery after a restart (form must require sign-in).
   - Webcam on a real camera, camera permission prompt.
   - Packaged `.dmg` install on a clean Mac; Windows `.exe` build (needs Wine + Rosetta on Apple Silicon, or a Windows PC).
   - A pilot with 3-5 students on both operating systems.
7. Housekeeping ideas: face detection on webcam photos, batch-wide reports, bulk "move students to batch N" admin action.

## MVP gap analysis (2026-10-13) — plan for next day
Verdict: ready for a 3-5 student LAN pilot; not for a high-stakes exam until P0 is done.

**P0 (before a real exam)**
- Real-hardware checks: Screen Recording permission, real screenshots, content protection, webcam, clean .dmg install, Google Form draft recovery after restart.
- Rebuild .dmg with BACKEND_URL=http://192.168.0.100:8000.
- Production server: gunicorn, WhiteNoise/collectstatic, HTTPS, real SECRET_KEY, DEBUG=0, TIME_ZONE.
- Backups of SQLite DB and media folder.
- Delete test data (TEST1, TEST2, test-both); set batches for math-101/physics-101; make test_user a teacher.

**P1 backend**: Redis/DB cache for throttles+lockouts; Postgres for >50 students; S3 option; scheduled purge_evidence; min client version check; "went offline at X for Y min" in timeline; logging/error tracking; clamp old timestamps.
**P1 student app**: offline notice; grace period if offline at time-out; Windows build (skipped for now); face/multi-person detection; accessibility.
**P1 teacher dashboard (user asked to make it nicer)**: summary cards on exam list; monitor status filter + search; coloured score pills; sticky header; timeline screenshot thumbnails + event icons; breadcrumbs/primary action; batch-wide reports; bulk move-students-to-batch; last-updated indicator; tablet layout.
**P2**: E2E test in CI (real Electron + backend); privacy/retention notice for students; teacher password self-reset + admin 2FA; download page; in-app help/support contact; grade export.

Suggested order: real-world checks -> rebuild dmg -> production setup + backups -> offline notice/grace -> teacher dashboard upgrade -> P2.
