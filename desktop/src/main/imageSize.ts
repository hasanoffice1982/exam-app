/** Scales (width, height) down to fit `maxWidth`, keeping the aspect ratio. Never scales up. */
export function fitWithin(width: number, height: number, maxWidth: number): { width: number; height: number } {
  if (width <= maxWidth) return { width: Math.round(width), height: Math.round(height) };
  const scale = maxWidth / width;
  return { width: Math.round(width * scale), height: Math.max(1, Math.round(height * scale)) };
}

export const clampQuality = (value: number): number => Math.min(100, Math.max(10, Math.round(value)));

/** Reads a positive integer from an env var, falling back when unset or invalid. */
export function envInt(raw: string | undefined, fallback: number): number {
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? Math.round(n) : fallback;
}
