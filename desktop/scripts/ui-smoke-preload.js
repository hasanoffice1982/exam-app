// Test-only preload: a scripted fake of the real bridge so the renderer UI can be driven without a server.
const { contextBridge } = require("electron");
const calls = [];
let loggedIn = false;
const ok = (data) => Promise.resolve({ ok: true, data });
const fail = (error) => Promise.resolve({ ok: false, error });
contextBridge.exposeInMainWorld("api", {
  acceptConsent: () => ok(),
  login: (roll, pw, hp) => { calls.push(["login", roll, pw, hp]); return pw === "good-pass" ? (loggedIn = true, ok({ roll_number: roll, name: "Ann Smith", batch: 81 })) : fail("Invalid roll number or password."); },
  activate: (roll, email, hp) => { calls.push(["activate", roll, email, hp]); return ok({ email: "a***@x.com" }); },
  getProfile: () => ok({ roll_number: "42", name: "Ann Smith", email: "a***@x.com", batch: 81 }),
  changePassword: (cur, next) => { calls.push(["change", cur, next]); return cur === "good-pass" ? ok() : fail("Your current password is not correct."); },
  logout: () => { calls.push(["logout"]); loggedIn = false; return ok(); },
  listExams: () => ok([
    { exam_id: "math", name: "Math", starts_at: null, ends_at: null, status: "open" },
    { exam_id: "phys", name: "Physics", starts_at: "2030-01-01T10:00:00Z", ends_at: null, status: "upcoming" },
  ]),
  startExam: () => ok(),
  __calls: () => calls,
});
