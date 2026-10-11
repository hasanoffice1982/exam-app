import { BACKEND_URL, REQUEST_TIMEOUT_MS } from "./config";

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

type LoginResponse = StudentProfile & { token: string };

let token: string | null = null;
export const setToken = (value: string | null): void => {
  token = value;
};

/** Network failures, timeouts, 5xx and rate limits are worth retrying; other 4xx are permanent. */
export function isRetryable(err: unknown): boolean {
  if (!(err instanceof ApiError)) return true;
  return err.status >= 500 || err.status === 429 || err.status === 408;
}

/** Turns a DRF error body ({detail} or {field: [msgs]}) into a readable message. */
async function errorMessage(res: Response, context: string): Promise<string> {
  const text = await res.text();
  try {
    const body = JSON.parse(text) as Record<string, unknown>;
    if (typeof body.detail === "string") return body.detail;
    const first = Object.values(body)[0];
    if (Array.isArray(first) && typeof first[0] === "string") return first[0];
  } catch {
    /* not JSON */
  }
  return `${context} -> ${res.status}`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${BACKEND_URL}${path}`, {
    ...init,
    headers,
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });
  if (!res.ok) throw new ApiError(await errorMessage(res, `${init.method ?? "GET"} ${path}`), res.status);
  return (await res.json()) as T;
}

function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export const api = {
  login: (rollNumber: string, password: string, honeypot: string) =>
    postJson<LoginResponse>("/api/login/", { roll_number: rollNumber, password, website: honeypot }),

  /** The server emails the password to the registered address; nothing secret comes back. */
  activate: (rollNumber: string, email: string, honeypot: string) =>
    postJson<{ detail: string; email: string }>("/api/auth/activate/", {
      roll_number: rollNumber,
      email,
      website: honeypot,
    }),

  getProfile: () => request<ProfileInfo>("/api/profile/"),

  changePassword: (currentPassword: string, newPassword: string) =>
    postJson("/api/auth/change-password/", { current_password: currentPassword, new_password: newPassword }),

  logout: () => postJson("/api/auth/logout/", {}),

  heartbeat: () => postJson("/api/heartbeat/", {}),

  listExams: () => request<ExamSummary[]>("/api/exams/"),

  /** Begins (or resumes) the single attempt for this exam; the server enforces batch, schedule and prior quits. */
  startExam: (examId: string) => postJson<ExamConfig>(`/api/exams/${encodeURIComponent(examId)}/start/`, {}),

  getConfig: (examId: string) => request<ExamConfig>(`/api/config/${encodeURIComponent(examId)}/`),

  postConsent: (examId: string, timestamp: string) => postJson("/api/consent/", { exam_id: examId, timestamp }),

  postEvent: (fields: Record<string, string>) => postJson("/api/events/", fields),

  uploadScreenshot: (fields: Record<string, string>, image: Buffer, filename: string, mime = "image/png") => {
    const form = new FormData();
    for (const [key, value] of Object.entries(fields)) form.append(key, value);
    form.append("file", new Blob([new Uint8Array(image)], { type: mime }), filename);
    return request("/api/screenshots/", { method: "POST", body: form });
  },
};
