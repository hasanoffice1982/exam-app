(() => {
  const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
  const input = (id: string) => $<HTMLInputElement>(id);

  const screens = ["consent", "login", "activate", "exam", "profile"].map((n) => $(`${n}-screen`));
  const errorEl = $("error");
  const infoEl = $("info");
  const examSelect = $<HTMLSelectElement>("exam");
  const examTime = $("exam-time");
  let exams: ExamSummary[] = [];
  let profile: StudentProfile | null = null;

  function setMessage(el: HTMLElement, message?: string): void {
    el.textContent = message ?? "";
    el.hidden = !message;
  }
  const showError = (m?: string) => setMessage(errorEl, m);
  const showInfo = (m?: string) => setMessage(infoEl, m);

  function show(name: string): void {
    for (const s of screens) s.hidden = s.id !== `${name}-screen`;
    showError();
  }

  /** Runs an async action with a button disabled; shows any error. Returns the result data. */
  async function submit<T>(btnId: string, action: () => Promise<IpcResult<T>>): Promise<T | undefined> {
    const btn = $<HTMLButtonElement>(btnId);
    showError();
    showInfo();
    btn.disabled = true;
    const res = await action();
    btn.disabled = false;
    if (!res.ok) {
      showError(res.error);
      return undefined;
    }
    return res.data as T;
  }

  const fmt = (iso: string) => new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });

  function describe(exam: ExamSummary): string {
    if (exam.status === "closed") return "ended";
    if (exam.status === "upcoming") return `starts ${fmt(exam.starts_at!)}`;
    return exam.ends_at ? `open, ends ${fmt(exam.ends_at)}` : "open";
  }

  async function goToExams(student: StudentProfile): Promise<void> {
    profile = student;
    $("e-name").textContent = student.name;
    show("exam");
    const res = await window.api.listExams();
    if (!res.ok || !res.data) return showError(`Could not load exams: ${res.error ?? "unknown error"}`);
    exams = res.data;
    examSelect.replaceChildren(new Option("Select an exam…", ""));
    for (const e of exams) {
      const option = new Option(`${e.name} (${describe(e)})`, e.exam_id);
      option.disabled = e.status !== "open";
      examSelect.add(option);
    }
  }

  examSelect.addEventListener("change", () => {
    const exam = exams.find((e) => e.exam_id === examSelect.value);
    examTime.textContent = exam
      ? `Starts: ${exam.starts_at ? fmt(exam.starts_at) : "any time"} · Ends: ${exam.ends_at ? fmt(exam.ends_at) : "no limit"}`
      : "";
  });

  $("start-btn").addEventListener("click", async () => {
    await window.api.acceptConsent();
    show("login");
  });

  $("to-activate").addEventListener("click", (e) => {
    e.preventDefault();
    input("a-roll").value = input("roll").value;
    show("activate");
  });

  $("to-login").addEventListener("click", (e) => {
    e.preventDefault();
    show("login");
  });

  $("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const profile = await submit("login-btn", () => window.api.login(input("roll").value, input("password").value, input("hp-login").value));
    if (profile) {
      input("password").value = "";
      void goToExams(profile);
    }
  });

  $("activate-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const result = await submit("activate-btn", () =>
      window.api.activate(input("a-roll").value, input("a-email").value, input("hp-activate").value),
    );
    if (!result) return;
    input("roll").value = input("a-roll").value;
    input("password").value = "";
    show("login");
    showInfo(`We emailed your password to ${result.email}. Check your inbox (and spam), then log in here.`);
  });

  $("to-profile").addEventListener("click", async (e) => {
    e.preventDefault();
    showInfo();
    const res = await window.api.getProfile();
    if (!res.ok || !res.data) return showError(res.error ?? "Could not load your profile");
    $("pf-name").textContent = res.data.name;
    $("pf-roll").textContent = res.data.roll_number;
    $("pf-batch").textContent = res.data.batch === null ? "–" : String(res.data.batch);
    $("pf-email").textContent = res.data.email || "–";
    show("profile");
  });

  $("profile-back").addEventListener("click", (e) => {
    e.preventDefault();
    showInfo();
    if (profile) void goToExams(profile);
  });

  $("logout-link").addEventListener("click", async (e) => {
    e.preventDefault();
    await window.api.logout();
    profile = null;
    exams = [];
    input("password").value = "";
    show("login");
    showInfo("You have been logged out.");
  });

  $("password-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    showInfo();
    const next = input("pw-new").value;
    if (next !== input("pw-confirm").value) return showError("The new passwords do not match.");
    const done = await submit("pw-btn", () => window.api.changePassword(input("pw-current").value, next));
    if (done === undefined && !errorEl.hidden) return; // submit() already showed the error
    (document.getElementById("password-form") as HTMLFormElement).reset();
    showInfo("Password changed. Use the new one next time you log in.");
  });

  $("exam-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await submit("begin-btn", () => window.api.startExam(examSelect.value));
  });
})();
