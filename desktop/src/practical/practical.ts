(() => {
  const $ = (id: string) => document.getElementById(id) as HTMLElement;
  const pad = (n: number) => String(n).padStart(2, "0");

  function formatRemaining(ms: number): string {
    const total = Math.max(0, Math.floor(ms / 1000));
    const h = Math.floor(total / 3600);
    return `${h ? `${h}:` : ""}${pad(Math.floor((total % 3600) / 60))}:${pad(total % 60)}`;
  }

  async function init(): Promise<void> {
    const info = await window.practical.getInfo();
    $("exam-name").textContent = info.examName;
    $("note").textContent = `Screenshots of your screen are taken about every ${info.screenshotSeconds} seconds while you work.`;
    if (info.instructions.trim()) {
      $("instructions").textContent = info.instructions;
      $("instructions-card").hidden = false;
    }
    if (info.url) {
      $("open-link").hidden = false;
      $("open-link").addEventListener("click", () => void window.practical.openLink());
    }
    $("finish").addEventListener("click", () => void window.practical.finish());

    const timer = $("timer");
    const tick = () => {
      if (info.endsAtMs === null) {
        timer.textContent = "No time limit";
        return;
      }
      const left = info.endsAtMs - Date.now();
      timer.textContent = formatRemaining(left);
      timer.classList.toggle("low", left <= 5 * 60 * 1000);
    };
    tick();
    setInterval(tick, 1000);
  }

  void init();
})();
