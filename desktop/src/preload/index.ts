import { contextBridge, ipcRenderer } from "electron";

const api: ExamBridge = {
  acceptConsent: () => ipcRenderer.invoke("consent:accept"),
  login: (rollNumber, password, honeypot) => ipcRenderer.invoke("auth:login", rollNumber, password, honeypot),
  activate: (rollNumber, email, honeypot) => ipcRenderer.invoke("auth:activate", rollNumber, email, honeypot),
  getProfile: () => ipcRenderer.invoke("profile:get"),
  changePassword: (currentPassword, newPassword) => ipcRenderer.invoke("auth:change-password", currentPassword, newPassword),
  logout: () => ipcRenderer.invoke("auth:logout"),
  listExams: () => ipcRenderer.invoke("exams:list"),
  startExam: (examId) => ipcRenderer.invoke("exam:start", examId),
};

contextBridge.exposeInMainWorld("api", api);
