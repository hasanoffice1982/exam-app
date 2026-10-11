/** Debounces "left the window": brief blurs shorter than the grace period are ignored. */
export class GraceTimer {
  private timer?: NodeJS.Timeout;

  constructor(private graceMs: number) {}

  setGraceMs(ms: number): void {
    this.graceMs = ms;
  }

  start(onExpire: () => void): void {
    this.cancel();
    this.timer = setTimeout(onExpire, this.graceMs);
  }

  cancel(): void {
    clearTimeout(this.timer);
    this.timer = undefined;
  }
}
