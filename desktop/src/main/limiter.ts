/** Allows at most one report per key per interval, so held-down keys don't flood the backend. */
export class AttemptLimiter {
  private last = new Map<string, number>();

  constructor(
    private readonly minIntervalMs = 5000,
    private readonly now: () => number = Date.now,
  ) {}

  allow(key: string): boolean {
    const t = this.now();
    const previous = this.last.get(key);
    if (previous !== undefined && t - previous < this.minIntervalMs) return false;
    this.last.set(key, t);
    return true;
  }
}
