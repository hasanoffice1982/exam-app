import { ApiError } from "./api";

const NETWORK_PATTERN = /fetch failed|ECONNREFUSED|ECONNRESET|ENOTFOUND|EAI_AGAIN|ETIMEDOUT|ENETUNREACH|EHOSTUNREACH|network|socket/i;

/** A message a student can act on: server messages as they are, network failures in plain words. */
export function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  const e = err as { name?: string; message?: string; cause?: { code?: string; message?: string } };
  const text = `${e?.message ?? ""} ${e?.cause?.code ?? ""} ${e?.cause?.message ?? ""}`;
  if (e?.name === "TimeoutError" || e?.name === "AbortError" || NETWORK_PATTERN.test(text)) {
    return "Cannot reach the exam server. Check your network connection and try again.";
  }
  return e?.message || String(err);
}
