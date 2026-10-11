import * as path from "path";

import { api, ApiError, isRetryable } from "./api";
import { Outcome, QueueItem } from "./queue";

/** Builds the queue sender. `onUnauthorized` fires when the session was revoked or expired. */
export function createSender(onUnauthorized: () => void) {
  return async (item: QueueItem, data?: Buffer): Promise<Outcome> => {
    const fields = { ...item.fields, client_id: item.id };
    try {
      if (item.kind === "screenshot") {
        const ext = item.file ? path.extname(item.file).toLowerCase() : ".png";
        const mime = ext === ".jpg" || ext === ".jpeg" ? "image/jpeg" : "image/png";
        await api.uploadScreenshot(fields, data ?? Buffer.alloc(0), `${item.id}${ext}`, mime);
      } else {
        await api.postEvent(fields);
      }
      return "done";
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onUnauthorized();
        return "drop";
      }
      console.error(`[sync] ${item.kind} ${isRetryable(err) ? "will retry" : "dropped"}:`, (err as Error).message);
      return isRetryable(err) ? "retry" : "drop";
    }
  };
}
