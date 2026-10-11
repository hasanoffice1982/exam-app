export const MIN_INTERVAL_SECONDS = 30;
const DARK_THRESHOLD = 8; // 0-255 average brightness below which the lens is treated as covered

/** Random delay around the interval (+/-50%) so students can't predict the next photo. */
export function nextDelayMs(intervalSeconds: number, random: () => number = Math.random): number {
  return Math.round(Math.max(MIN_INTERVAL_SECONDS, intervalSeconds) * 1000 * (0.5 + random()));
}

export function dataUrlToBuffer(dataUrl: string): Buffer {
  const match = /^data:image\/jpeg;base64,(.+)$/.exec(dataUrl);
  if (!match) throw new Error("Camera returned an unexpected image format");
  const buffer = Buffer.from(match[1], "base64");
  if (buffer.length === 0) throw new Error("Camera returned an empty image");
  return buffer;
}

/** Mean brightness (0-255) of a BGRA/RGBA bitmap, ignoring alpha. */
export function averageBrightness(bitmap: Buffer): number {
  let sum = 0;
  let pixels = 0;
  for (let i = 0; i + 3 < bitmap.length; i += 4) {
    sum += (bitmap[i] + bitmap[i + 1] + bitmap[i + 2]) / 3;
    pixels++;
  }
  return pixels ? sum / pixels : 0;
}

export const isTooDark = (average: number): boolean => average < DARK_THRESHOLD;

/** Rejects if `work` doesn't settle in time (e.g. a permission prompt nobody answers). */
export function withTimeout<T>(work: Promise<T>, ms: number, message: string): Promise<T> {
  let timer: NodeJS.Timeout;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error(message)), ms);
  });
  return Promise.race([work, timeout]).finally(() => clearTimeout(timer));
}

/** Short reason that is safe to show the student and to store as event detail. */
export function friendlyCameraError(raw: string): string {
  if (/NotAllowed|denied|permission/i.test(raw)) return "Camera access was denied";
  if (/NotFound|no camera|DevicesNotFound/i.test(raw)) return "No camera found";
  if (/NotReadable|in use|busy/i.test(raw)) return "Camera is in use by another app";
  if (/did not respond/i.test(raw)) return "Camera did not respond";
  if (/covered|black/i.test(raw)) return "Camera image is black (lens covered?)";
  return raw.replace(/^(Error( invoking remote method '[^']*')?:\s*)+/i, "").slice(0, 100) || "Camera error";
}
