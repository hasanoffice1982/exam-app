# ExamProctor manuals

Three separate, self-contained PDF manuals, each with real screenshots and numbered call-outs.

| Manual | For | What it covers |
|---|---|---|
| [Administrator Manual](admin-manual.pdf) | The person who owns the system | How the system fits together, logging in, the admin site tour, students (CSV import, batches, passwords), exams (every setting), teachers, running an exam, after the exam (archive, evidence, audit), server settings, backups, troubleshooting |
| [Teacher Manual](teacher-manual.pdf) | Subject teachers | Logging in, your exams, exam settings, passwords, the live monitor (every column, button and event), reviewing a student, practical exams, marks from Google Forms, archive and clean-up, FAQs |
| [Student Guide](student-manual.pdf) | Students | Installing the Mac app, permissions, login and first-time password, starting an exam, the written and practical parts, warnings, time, what to do when something goes wrong, profile and password, privacy, and a one-page Bangla guide |

The screenshots come from the real admin site, teacher dashboard and student app running against a **throwaway demo database** (`manage.py seed_demo`). Pop-up dialogs drawn by macOS cannot be screenshotted, so they are redrawn with the exact wording from the code and labelled "Illustration".

## Folder layout

```
manuals/
  admin-manual.pdf  teacher-manual.pdf  student-manual.pdf   the deliverables
  images/{admin,teacher,student}/                              every screenshot used
  src/
    content/{admin,teacher,student}.js                         the text of each manual (edit these)
    build.js                                                   turns content into A4 PDFs
    capture-web.js  capture-app.js  capture-illustrations.js   screenshot scripts (run inside Electron)
    make-sample-images.js  sample/  sample-form/               sample evidence images and example Google-Form-like page
    demo-env.sh  run-all.sh                                    start the demo and rebuild everything
```

## Rebuild everything

From the repository root (needs the backend virtualenv and `npm install` in `desktop/`):

```bash
bash manuals/src/run-all.sh
```

This builds the app, starts an isolated demo server (own database in `/tmp/examapp-demo`, ports 8780/8781), seeds demo data, captures every screenshot, and writes the three PDFs. It never touches your real database. The demo logins (demo database only) are `admin` / `Admin-demo-1`, teachers `rahman` / `Rahman-demo-1` and `sultana` / `Sultana-demo-1`, and students `81001`...`81009` / `Demo-pass-1`.

To change wording only, edit a file in `src/content/` and run `cd desktop && npx electron ../manuals/src/build.js` (add `admin`, `teacher` or `student` to build just one).
