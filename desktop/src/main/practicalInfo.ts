/** What the practical window shows. The deadline uses the server's clock so a wrong student clock can't stretch it. */
export function buildPracticalInfo(config: ExamConfig, now: number = Date.now()): PracticalInfo {
  const offset = Date.parse(config.server_time) - now;
  return {
    examName: config.name,
    instructions: config.practical_instructions,
    url: config.practical_url,
    endsAtMs: config.ends_at ? Date.parse(config.ends_at) - offset : null,
    screenshotSeconds: config.practical_screenshot_seconds,
  };
}

/** Only plain web links may be opened from the practical window. */
export function isOpenableLink(url: string): boolean {
  try {
    return ["https:", "http:"].includes(new URL(url).protocol);
  } catch {
    return false;
  }
}
