import { contextBridge, ipcRenderer } from "electron";

const practical: PracticalBridge = {
  getInfo: async () => ((await ipcRenderer.invoke("practical:info")) as IpcResult<PracticalInfo>).data as PracticalInfo,
  finish: () => ipcRenderer.invoke("practical:finish"),
  openLink: () => ipcRenderer.invoke("practical:open-link"),
};

contextBridge.exposeInMainWorld("practical", practical);
