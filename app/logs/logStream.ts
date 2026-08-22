export type LogLevel = "debug" | "info" | "warning" | "error" | "critical";

export type RuntimeLogEvent = {
  cursor: string;
  occurred_at: string;
  received_at: string;
  source_type: "backend" | "client" | "system";
  source: string;
  level: LogLevel;
  category: string;
  message: string;
  context: Record<string, unknown>;
  truncated: boolean;
};

export type SseEnvelope = {
  event: string;
  id?: string;
  data: unknown;
};

export class SseParser {
  private buffer = "";

  push(chunk: string): SseEnvelope[] {
    this.buffer = `${this.buffer}${chunk}`.replace(/\r\n/g, "\n");
    const envelopes: SseEnvelope[] = [];
    let boundary = this.buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const block = this.buffer.slice(0, boundary);
      this.buffer = this.buffer.slice(boundary + 2);
      const envelope = parseSseBlock(block);
      if (envelope) envelopes.push(envelope);
      boundary = this.buffer.indexOf("\n\n");
    }
    return envelopes;
  }
}

export function parseSseBlock(block: string): SseEnvelope | null {
  if (!block.trim() || block.trimStart().startsWith(":")) return null;
  let event = "message";
  let id: string | undefined;
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("id:")) id = line.slice(3).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  const serialized = data.join("\n");
  if (!serialized) return { event, id, data: null };
  try {
    return { event, id, data: JSON.parse(serialized) };
  } catch {
    return { event, id, data: serialized };
  }
}

export function appendBounded(
  current: RuntimeLogEvent[],
  incoming: RuntimeLogEvent[],
  limit = 600,
): RuntimeLogEvent[] {
  if (!incoming.length) return current;
  const combined = [...current, ...incoming];
  return combined.length > limit ? combined.slice(combined.length - limit) : combined;
}

export function filterLogEvents(
  rows: RuntimeLogEvent[],
  levels: ReadonlySet<LogLevel>,
  keyword: string,
): RuntimeLogEvent[] {
  const term = keyword.trim().toLocaleLowerCase();
  return rows.filter((row) => {
    if (!levels.has(row.level)) return false;
    if (!term) return true;
    const context = JSON.stringify(row.context).toLocaleLowerCase();
    return `${row.message}\n${row.category}\n${row.source}`.toLocaleLowerCase().includes(term) || context.includes(term);
  });
}

export class PauseBuffer {
  private rows: RuntimeLogEvent[] = [];
  private readonly limit: number;
  skipped = 0;

  constructor(limit = 240) {
    this.limit = limit;
  }

  get size(): number {
    return this.rows.length;
  }

  push(event: RuntimeLogEvent): void {
    this.rows.push(event);
    if (this.rows.length > this.limit) {
      this.rows.splice(0, this.rows.length - this.limit);
      this.skipped += 1;
    }
  }

  drain(): RuntimeLogEvent[] {
    const pending = this.rows;
    this.rows = [];
    return pending;
  }

  clear(): void {
    this.rows = [];
    this.skipped = 0;
  }
}

export function nextReconnectDelay(attempt: number): number {
  return Math.min(12_000, 700 * 2 ** Math.min(Math.max(0, attempt), 5));
}
