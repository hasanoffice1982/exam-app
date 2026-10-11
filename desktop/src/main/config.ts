import * as dotenv from "dotenv";
import * as path from "path";

dotenv.config({ path: path.join(__dirname, "..", "..", ".env") });

export const BACKEND_URL = (process.env.BACKEND_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");
import { clampQuality, envInt } from "./imageSize";

// Screenshots are downscaled and saved as JPEG: ~10x smaller than full-resolution PNG, still readable.
export const SCREENSHOT_MAX_WIDTH = envInt(process.env.SCREENSHOT_MAX_WIDTH, 1280);
export const SCREENSHOT_JPEG_QUALITY = clampQuality(envInt(process.env.SCREENSHOT_JPEG_QUALITY, 70));
export const CONFIG_POLL_INTERVAL_MS = 2 * 60 * 1000;
export const HEARTBEAT_INTERVAL_MS = 30_000;
export const PROCESS_SCAN_INTERVAL_MS = 30_000;
export const REQUEST_TIMEOUT_MS = 15_000;
// Delay so the screenshot shows what the student switched *to*, not the exam window.
export const SCREENSHOT_DELAY_MS = 300;
