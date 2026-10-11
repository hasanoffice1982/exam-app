# Project review: how it works, what was checked, what to know

Reviewed end to end (backend, desktop app, teacher dashboard, admin, docs) and exercised against a live server.
Verification: **331 backend tests**, **63 desktop tests**, three real-Electron smoke runs (stage hand-over, quit-while-offline, student screens) and a **24-step live scenario** (real HTTP, real app code, real database) covering login, exam start, evidence upload, replay, forged events, teacher actions, force-end, restart, extra time, archive and CSV.

## 1. How it works

```
Student app (Electron, Mac)  <-->  Django server (API + SQLite + media)  <-->  Teacher dashboard (/teacher/)  and  Admin (/admin/)
```

1. **Admin** creates students (CSV or form) with a *batch*, exams (each with exactly one batch, a written and/or practical part, schedule, monitoring, webcam), and teacher accounts.
2. **Passwords**: emailed on first activation, or a one-time printed sheet from an admin/teacher. Only hashes are stored.
3. **Student** logs in (one session per student, bearer token held only in the app's main process), picks an exam of their batch, presses *Begin*. The app checks the environment (one screen for the written part, no screen-share/remote/recording apps, Screen Recording permission, camera if required) and creates the attempt on the server.
4. **Written part**: locked full-screen Google Form. Leaving the window records an event and a screenshot after a grace period; copy/paste, developer tools, print/save and other sites are blocked. Submitting the form is detected and the student moves to the practical part (or finishes).
5. **Practical part**: a normal window with timer and instructions; screenshots on a timer; switching apps is allowed.
6. Everything the app sends goes through a **durable on-disk queue** (idempotent client ids, retried, drained before quitting, delivered before the next start). A heartbeat every 30 s shows the teacher who is online.
7. **Teacher** watches the live monitor (flag/score per student), reviews timelines, gives extra time, ends/restarts attempts, moves students on, builds marks from the Google Form CSV, archives, and deletes evidence.
8. **After**: archive, delete screenshots/photos after the retention period (audit-logged), deactivate the batch.

## 2. Scenarios and what happens

| Situation | Behaviour | Covered by |
|---|---|---|
| Internet drops mid-exam | Window keeps running; events/screenshots queue on disk; teacher sees *offline*; everything is sent in order, once, on reconnect | queue tests, live outage test, E2E |
| App or computer crashes | Student logs in again and resumes the same part; a *restart* is logged (score unaffected) | attempt tests, E2E |
| Student quits (or closes the window and confirms) | `exam_quit` ends the attempt, final until a teacher resets; if the quit event was still queued offline, it is delivered **before** the next start so they are refused | tests, quit-offline smoke |
| Student runs out of time | Server-clock deadline; window closes with a message; per-student extra time possible | extra-time tests |
| Teacher ends an attempt | Session revoked immediately, window closes within ~30 s, re-entry blocked; reset lets them restart | tests, E2E |
| Student logs in on a second computer | First session ends | auth tests |
| Wrong/forgotten password | Per-address lockout (5 tries, 15 min) so a classmate cannot lock someone else out; teacher "New password"; admin reset | lockout tests |
| Student not in the exam's batch | Cannot see, open, start or post events for it | batch tests |
| Exam has no batch / archived | Invisible to students; teachers see a warning group / archived list | tests |
| Google Form fails to load at the start | Retried every 5 s; crashed page reloads | unit test (rule), code |
| Form submission not detected | Teacher "To practical" (or the config poll moves the window on) | stage tests |
| Screen Recording off | Blocked at start (macOS prompt triggered); mid-exam failures logged as *Screenshot could not be taken* | code, event tests |
| Extra monitor / blocked app | Written part will not start; mid-exam noted with a warning; practical allows a second monitor | process/hardening tests |
| Teacher session expires on the monitor | Page says so instead of silently going stale | test |
| Bangla/other non-English names in Excel | CSVs carry a UTF-8 BOM | tests, live check |
| Roll numbers such as `2021/001` | Work in login and in dashboard links | tests |

## 3. Issues found in this review (all fixed, with tests)

1. A student could post teacher-only events (`force_ended`, `time_extended`...) or events into **another batch's exam**. Now only the app's event types are accepted and the exam must be the student's own.
2. A student could upload a file named `.html` as an "image" that a teacher's browser might render. Uploads now need a real PNG/JPEG signature and extension, and files are served with a fixed safe type and a locked-down policy.
3. Failing five logins could **lock a classmate out** just before an exam. Lockouts are now per address (plus a high per-roll ceiling against distributed guessing).
4. The last events (`quit`, `finished`) could be lost if the app closed while slow or offline. They are now flushed before quitting and before the next start.
5. A wrong student clock could get events rejected. Future timestamps are clamped, never dropped.
6. The API let an admin key save an exam configuration the admin pages would refuse (no parts, empty form link). It now applies the same rules.
7. Archiving was blocked forever by students who never reported an ending. After the exam's time is over they are completed automatically (audit-logged).
8. Teachers could not help a student who forgot a password. Added *Students & passwords* with a per-student new password.
9. A wrongly entered batch could never be lowered. Admins can now correct it explicitly (recorded as a correction); the forward-only rule otherwise stands.
10. Roll numbers containing `/` broke the timeline link; CSVs garbled Bangla in Excel; an exam window left on an error page if offline at the start; screenshot failures were invisible to teachers; raw "fetch failed" was shown to students; SQLite could throw "database is locked" under classroom load (now WAL + timeout); a silent stale monitor after session expiry.

## 4. Known limits (be aware, not defects)

- **Client-side enforcement can be bypassed** by a determined student: a modified client, a second device, or a phone pointed at the screen cannot be prevented by software. The system is a deterrent plus an audit trail.
- **HTTP on the school network** sends passwords and tokens unencrypted. Fine on a trusted LAN; use HTTPS for anything wider.
- **Lockout and rate-limit counters live in memory** (reset on a server restart; per worker if you run several). Use Redis for a multi-worker deployment.
- **SQLite** is right for one classroom server (tens of students). Move to PostgreSQL if you grow far beyond that.
- **Behind a reverse proxy** the real client address must be forwarded, or per-address limits see everyone as one.
- **Mac only so far.** A Windows installer has not been built or tested. The app is unsigned (one-time macOS warning, steps in the student guide).
- **Google Form submission** is recognised by its `formResponse` page; the teacher's *To practical* button is the fallback. Draft recovery after a crash needs the form to require sign-in (test once).
- **Marks tool** matches by roll number and applies the policy (quit = 0, ended/no submission = blank); practical work is marked by the teacher from the evidence.
- **Face detection** is not included; webcam photos are for human review.
- **macOS permissions** (Screen Recording, Camera) cannot be granted by the app; it checks and explains.

## 5. Before going live

1. Set `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0`, `DJANGO_ALLOWED_HOSTS`, `TIME_ZONE`, and the `EMAIL_*` variables (or use hand-out sheets); run `python manage.py check`.
2. Run the server with gunicorn (2+ workers), serve static files (`collectstatic`), keep the machine awake, back up `db.sqlite3` and `media/`.
3. Set every exam's batch; give students passwords; build the installer with the real `BACKEND_URL`.
4. Pilot with a few students on real Macs and a real Google Form: permissions, form-submission detection, draft recovery, webcam.
