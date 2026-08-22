import assert from "node:assert/strict";
import test from "node:test";

import {
  appendBounded,
  appendUniqueBounded,
  filterLogEvents,
  type LogLevel,
  nextReconnectDelay,
  PauseBuffer,
  type RuntimeLogEvent,
  SseParser,
} from "../app/logs/logStream.ts";

function event(cursor: string, level: LogLevel, message: string): RuntimeLogEvent {
  return {
    cursor,
    occurred_at: "2026-08-22T04:00:00Z",
    received_at: "2026-08-22T04:00:01Z",
    source_type: "client",
    source: "deeptravel-flutter",
    level,
    category: "network",
    message,
    context: { session_id: "session-1" },
    truncated: false,
  };
}

test("parses SSE frames split across network chunks", () => {
  const parser = new SseParser();
  assert.deepEqual(parser.push("id: 8\nevent: lo"), []);
  const frames = parser.push('g\ndata: {"cursor":"8","message":"你好"}\n\n');
  assert.equal(frames.length, 1);
  assert.equal(frames[0].event, "log");
  assert.equal(frames[0].id, "8");
  assert.deepEqual(frames[0].data, { cursor: "8", message: "你好" });
});

test("bounds rows and applies level and keyword filters", () => {
  const rows = appendBounded(
    [event("1", "info", "started")],
    [event("2", "warning", "slow request"), event("3", "error", "request failed")],
    2,
  );
  assert.deepEqual(rows.map((row) => row.cursor), ["2", "3"]);
  assert.deepEqual(
    filterLogEvents(rows, new Set<LogLevel>(["error"]), "session-1").map((row) => row.cursor),
    ["3"],
  );
  assert.deepEqual(filterLogEvents(rows, new Set<LogLevel>(["warning", "error"]), "slow").map((row) => row.cursor), ["2"]);
});

test("deduplicates cursor-resumed client events", () => {
  const rows = appendUniqueBounded(
    [event("7", "info", "already visible")],
    [event("7", "info", "already visible"), event("8", "error", "new event")],
  );
  assert.deepEqual(rows.map((row) => row.cursor), ["7", "8"]);
});

test("buffers paused events, reports overflow, clears locally, and caps reconnect delay", () => {
  const pending = new PauseBuffer(2);
  pending.push(event("1", "info", "one"));
  pending.push(event("2", "warning", "two"));
  pending.push(event("3", "error", "three"));
  assert.equal(pending.size, 2);
  assert.equal(pending.skipped, 1);
  assert.deepEqual(pending.drain().map((row) => row.cursor), ["2", "3"]);
  assert.equal(pending.size, 0);

  pending.push(event("4", "info", "four"));
  pending.clear();
  assert.equal(pending.size, 0);
  assert.equal(pending.skipped, 0);
  assert.equal(nextReconnectDelay(0), 700);
  assert.equal(nextReconnectDelay(20), 12_000);
});
