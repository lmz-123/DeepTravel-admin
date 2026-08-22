"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  appendBounded,
  filterLogEvents,
  LogLevel,
  nextReconnectDelay,
  PauseBuffer,
  RuntimeLogEvent,
  SseParser,
} from "./logStream.ts";

type BackendSource = { id: string; label: string; available: boolean };
type SourceResponse = {
  client: { id: string; label: string; available: boolean };
  backend: BackendSource[];
  limits: { tail: number; max_streams: number; retention_days: number };
};
type ConnectionState = "idle" | "connecting" | "connected" | "reconnecting" | "unavailable";

const levels: LogLevel[] = ["debug", "info", "warning", "error", "critical"];
const levelLabels: Record<LogLevel, string> = {
  debug: "调试",
  info: "信息",
  warning: "警告",
  error: "错误",
  critical: "严重",
};
const stateLabels: Record<ConnectionState, string> = {
  idle: "等待连接",
  connecting: "正在连接",
  connected: "实时连接",
  reconnecting: "正在重连",
  unavailable: "来源不可用",
};

export default function LogConsole({ apiBase, token, onNotice }: { apiBase: string; token: string; onNotice: (message: string) => void }) {
  const [sources, setSources] = useState<SourceResponse | null>(null);
  const [selected, setSelected] = useState("client");
  const [rows, setRows] = useState<RuntimeLogEvent[]>([]);
  const [enabledLevels, setEnabledLevels] = useState<Set<LogLevel>>(() => new Set(levels));
  const [keyword, setKeyword] = useState("");
  const [paused, setPaused] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const [connection, setConnection] = useState<ConnectionState>("idle");
  const [pendingCount, setPendingCount] = useState(0);
  const [skippedCount, setSkippedCount] = useState(0);
  const pausedRef = useRef(false);
  const pendingRef = useRef(new PauseBuffer(240));
  const cursorRef = useRef<string | null>(null);
  const viewportRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    async function loadSources() {
      try {
        const response = await fetch(`${apiBase.replace(/\/$/, "")}/logs/sources`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`日志来源读取失败 (${response.status})`);
        const data = await response.json() as SourceResponse;
        setSources(data);
        const firstBackend = data.backend.find((source) => source.available);
        setSelected(firstBackend ? `backend:${firstBackend.id}` : "client");
      } catch (error) {
        if ((error as Error).name !== "AbortError") {
          setConnection("unavailable");
          onNotice(error instanceof Error ? error.message : "无法读取日志来源");
        }
      }
    }
    void loadSources();
    return () => controller.abort();
  }, [apiBase, token, onNotice]);

  useEffect(() => {
    if (!sources || !selected) return;
    const controller = new AbortController();
    const decoder = new TextDecoder();
    let retry = 0;
    let stopped = false;
    cursorRef.current = null;
    pendingRef.current.clear();

    function accept(event: RuntimeLogEvent) {
      if (event.source_type === "client") cursorRef.current = event.cursor;
      if (pausedRef.current) {
        pendingRef.current.push(event);
        setPendingCount(pendingRef.current.size);
        setSkippedCount(pendingRef.current.skipped);
        return;
      }
      setRows((current) => appendBounded(current, [event]));
    }

    async function connect() {
      while (!controller.signal.aborted && !stopped) {
        setConnection(retry ? "reconnecting" : "connecting");
        const isClient = selected === "client";
        const path = isClient
          ? `/logs/client/stream?tail=240${cursorRef.current ? `&after=${encodeURIComponent(cursorRef.current)}` : ""}`
          : `/logs/backend/stream?source=${encodeURIComponent(selected.slice("backend:".length))}&tail=240`;
        try {
          const response = await fetch(`${apiBase.replace(/\/$/, "")}${path}`, {
            headers: { Authorization: `Bearer ${token}`, Accept: "text/event-stream" },
            cache: "no-store",
            signal: controller.signal,
          });
          if (!response.ok || !response.body) {
            const detail = await response.json().catch(() => ({ detail: `日志连接失败 (${response.status})` }));
            throw new Error(String(detail.detail || `日志连接失败 (${response.status})`));
          }
          setConnection("connected");
          retry = 0;
          const reader = response.body.getReader();
          const parser = new SseParser();
          while (!controller.signal.aborted) {
            const { done, value } = await reader.read();
            if (done) break;
            for (const envelope of parser.push(decoder.decode(value, { stream: true }))) {
              if (envelope.event === "log" && envelope.data && typeof envelope.data === "object") {
                accept(envelope.data as RuntimeLogEvent);
              } else if (envelope.event === "source_status") {
                setConnection("unavailable");
              }
            }
          }
        } catch (error) {
          if (controller.signal.aborted || (error as Error).name === "AbortError") return;
          setConnection("reconnecting");
          if (retry === 0) onNotice(error instanceof Error ? error.message : "实时日志连接中断");
        }
        retry += 1;
        const delay = nextReconnectDelay(retry);
        await new Promise<void>((resolve) => {
          const timer = window.setTimeout(resolve, delay);
          controller.signal.addEventListener("abort", () => { window.clearTimeout(timer); resolve(); }, { once: true });
        });
      }
    }

    void connect();
    return () => { stopped = true; controller.abort(); };
  }, [apiBase, token, selected, sources, onNotice]);

  useEffect(() => {
    if (!autoScroll || paused || !viewportRef.current) return;
    viewportRef.current.scrollTo({ top: viewportRef.current.scrollHeight, behavior: "smooth" });
  }, [rows, autoScroll, paused]);

  const visibleRows = useMemo(() => filterLogEvents(rows, enabledLevels, keyword), [rows, enabledLevels, keyword]);

  function togglePause() {
    if (pausedRef.current) {
      pausedRef.current = false;
      setPaused(false);
      setRows((current) => appendBounded(current, pendingRef.current.drain()));
      setPendingCount(0);
    } else {
      pausedRef.current = true;
      setPaused(true);
    }
  }

  function clearView() {
    setRows([]);
    pendingRef.current.clear();
    setPendingCount(0);
    setSkippedCount(0);
  }

  function chooseSource(value: string) {
    cursorRef.current = null;
    pendingRef.current.clear();
    setRows([]);
    setPendingCount(0);
    setSkippedCount(0);
    setSelected(value);
  }

  function toggleLevel(level: LogLevel) {
    setEnabledLevels((current) => {
      const next = new Set(current);
      if (next.has(level)) next.delete(level); else next.add(level);
      return next;
    });
  }

  return <section className="log-console" aria-label="实时运行日志">
    <div className="log-summary">
      <div><p className="eyebrow">LIVE OBSERVABILITY</p><h2>运行状态流</h2><p>后端输出即时跟随；客户端记录保留 {sources?.limits.retention_days ?? "—"} 天。</p></div>
      <div className={`stream-state ${connection}`} role="status"><i />{paused ? "已暂停显示" : stateLabels[connection]}</div>
    </div>

    <div className="log-toolbar">
      <label className="log-source-field"><span>日志来源</span><select value={selected} onChange={(event) => chooseSource(event.target.value)} aria-label="选择日志来源">
        <option value="client">客户端 · Flutter</option>
        {sources?.backend.map((source) => <option value={`backend:${source.id}`} disabled={!source.available} key={source.id}>后端 · {source.label}{source.available ? "" : "（不可用）"}</option>)}
      </select></label>
      <label className="log-search"><span className="sr-only">搜索日志</span><input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="搜索消息、分类或会话…" /></label>
      <div className="log-actions">
        <button className={paused ? "primary-button" : "ghost-button"} onClick={togglePause} aria-pressed={paused}>{paused ? `继续${pendingCount ? ` · ${pendingCount}` : ""}` : "暂停"}</button>
        <button className="ghost-button" onClick={clearView}>清空视图</button>
      </div>
    </div>

    <div className="level-filters" aria-label="日志级别筛选">
      {levels.map((level) => <button className={enabledLevels.has(level) ? `level-chip ${level} active` : `level-chip ${level}`} aria-pressed={enabledLevels.has(level)} onClick={() => toggleLevel(level)} key={level}><i />{levelLabels[level]}</button>)}
      <label className="auto-scroll"><input type="checkbox" checked={autoScroll} onChange={(event) => setAutoScroll(event.target.checked)} />自动滚动</label>
      <span className="log-count">显示 {visibleRows.length} / 已接收 {rows.length}{skippedCount ? ` · 跳过 ${skippedCount}` : ""}</span>
    </div>

    {/* Keyboard focus is required so non-pointer users can scroll this live region. */}
    {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
    <div className="log-viewport" ref={viewportRef} role="region" tabIndex={0} aria-label="日志内容，可使用方向键滚动" aria-live={paused ? "off" : "polite"}>
      {visibleRows.map((row, index) => <article className={`log-row ${row.level}`} key={`${row.cursor}-${index}`}>
        <time dateTime={row.occurred_at}>{formatTime(row.occurred_at)}</time>
        <span className="log-level">{row.level.toUpperCase()}</span>
        <span className="log-origin">{row.source}<small>{row.category}</small></span>
        <div className="log-message"><p>{row.message}{row.truncated && <em> 已截断</em>}</p>{Object.keys(row.context || {}).length > 0 && <details><summary>上下文</summary><pre>{JSON.stringify(row.context, null, 2)}</pre></details>}</div>
      </article>)}
      {!visibleRows.length && <div className="log-empty"><span>⌁</span><strong>{connection === "connected" ? "等待新的日志事件" : "正在建立日志连接"}</strong><small>这里不会填充演示数据</small></div>}
    </div>
  </section>;
}

function formatTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(date);
}
