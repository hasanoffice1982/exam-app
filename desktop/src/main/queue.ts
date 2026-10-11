import { promises as fs } from "fs";
import * as path from "path";

export type Outcome = "done" | "retry" | "drop";

export interface QueueItem {
  id: string; // also sent as client_id, so a retried upload is deduplicated server-side
  owner: string; // roll number: identity comes from the session token, so never send someone else's items
  kind: "event" | "screenshot";
  fields: Record<string, string>;
  file?: string;
}

export type Sender = (item: QueueItem, data?: Buffer) => Promise<Outcome>;

/** Durable FIFO of pending uploads. Survives offline periods and app restarts. */
export class UploadQueue {
  private items: QueueItem[] = [];
  private flushing = false;
  private writing: Promise<void> = Promise.resolve();
  private timer?: NodeJS.Timeout;
  private readonly indexFile: string;
  private readonly filesDir: string;

  constructor(
    dir: string,
    private readonly owner: string,
    private readonly send: Sender,
    private readonly maxItems = 500,
  ) {
    this.indexFile = path.join(dir, "queue.json");
    this.filesDir = path.join(dir, "files");
  }

  async init(): Promise<void> {
    await fs.mkdir(this.filesDir, { recursive: true });
    try {
      this.items = JSON.parse(await fs.readFile(this.indexFile, "utf8")) as QueueItem[];
    } catch {
      this.items = [];
    }
  }

  pending(): number {
    return this.items.filter((i) => i.owner === this.owner).length;
  }

  async enqueue(item: Omit<QueueItem, "owner" | "file">, data?: Buffer, ext = "png"): Promise<void> {
    const entry: QueueItem = { ...item, owner: this.owner };
    if (data) {
      entry.file = path.join(this.filesDir, `${item.id}.${ext}`);
      await fs.writeFile(entry.file, data);
    }
    this.items.push(entry);
    while (this.items.length > this.maxItems) await this.remove(this.items[0]);
    await this.persist();
  }

  /** Sends own items in order; stops at the first one that needs a retry. */
  async flush(): Promise<void> {
    if (this.flushing) return;
    this.flushing = true;
    try {
      for (const item of this.items.filter((i) => i.owner === this.owner)) {
        let data: Buffer | undefined;
        if (item.file) {
          try {
            data = await fs.readFile(item.file);
          } catch {
            await this.remove(item); // file vanished: nothing left to upload
            continue;
          }
        }
        const outcome = await this.send(item, data);
        if (outcome === "retry") break;
        await this.remove(item);
      }
      await this.persist();
    } finally {
      this.flushing = false;
    }
  }

  startTimer(intervalMs: number): void {
    this.timer = setInterval(() => void this.flush(), intervalMs);
  }

  stopTimer(): void {
    clearInterval(this.timer);
  }

  private async remove(item: QueueItem): Promise<void> {
    this.items = this.items.filter((i) => i !== item);
    if (item.file) await fs.unlink(item.file).catch(() => undefined);
  }

  private persist(): Promise<void> {
    const snapshot = JSON.stringify(this.items);
    this.writing = this.writing.then(async () => {
      const tmp = `${this.indexFile}.tmp`;
      await fs.writeFile(tmp, snapshot);
      await fs.rename(tmp, this.indexFile);
    });
    return this.writing;
  }
}
