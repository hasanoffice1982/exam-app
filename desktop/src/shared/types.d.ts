// Ambient types shared by main, preload and renderer (no runtime code).
type ExamStatus = "upcoming" | "open" | "closed";

interface ExamSummary {
  exam_id: string;
  name: string;
  starts_at: string | null;
  ends_at: string | null;
  status: ExamStatus;
}

interface ExamConfig {
  monitoring_enabled: boolean;
  form_url: string;
  mode: string;
  starts_at: string | null;
  ends_at: string | null;
  grace_seconds: number;
  webcam_enabled: boolean;
  webcam_interval_seconds: number;
  status: ExamStatus;
  server_time: string;
}

interface StudentProfile {
  roll_number: string;
  name: string;
  batch?: number | null;
}

interface ProfileInfo {
  roll_number: string;
  name: string;
  email: string; // masked
  batch: number | null;
}

interface IpcResult<T = undefined> {
  ok: boolean;
  error?: string;
  data?: T;
}

interface ExamBridge {
  acceptConsent(): Promise<IpcResult>;
  login(rollNumber: string, password: string, honeypot: string): Promise<IpcResult<StudentProfile>>;
  /** Asks the server to email the student their password; resolves with the masked address. */
  activate(rollNumber: string, email: string, honeypot: string): Promise<IpcResult<{ email: string }>>;
  getProfile(): Promise<IpcResult<ProfileInfo>>;
  changePassword(currentPassword: string, newPassword: string): Promise<IpcResult>;
  logout(): Promise<IpcResult>;
  listExams(): Promise<IpcResult<ExamSummary[]>>;
  startExam(examId: string): Promise<IpcResult>;
}

interface Window {
  api: ExamBridge;
}
