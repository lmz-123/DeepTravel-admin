"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  appendUniqueBounded,
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
  const [backendSource, setBackendSource] = useState("");
  const [enabledLevels, setEnabledLevels] = useState<Set<LogLevel>>(() => new Set(levels));
  const [keyword, setKeyword] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    async function loadSources() {
      try {
        const response = await fetch(`${apiBase.replace(/\/$/, "")}/logs/sources`, {
          headers: { Authorization: `Bearer ${token}` },
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`日志来源读取失败 (${response.status})`);
        const data = await response.json() as SourceResponse;
        setSources(data);
        setBackendSource((current) => current && data.backend.some((source) => source.id === current)
          ? current
          : data.backend.find((source) => source.available)?.id ?? data.backend[0]?.id ?? "");
      } catch (error) {
        if ((error as Error).name !== "AbortError") {
          onNotice(error instanceof Error ? error.message : "无法读取日志来源");
        }
      }
    }
    void loadSources();
    return () => controller.abort();
  }, [apiBase, token, onNotice]);

  function toggleLevel(level: LogLevel) {
    setEnabledLevels((current) => {
      const next = new Set(current);
      if (next.has(level)) next.delete(level); else next.add(level);
      return next;
    });
  }

  const selectedBackend = sources?.backend.find((source) => source.id === backendSource);
  return <section className="log-console" aria-label="实时运行日志">
    <div className="log-summary">
      <div><p className="eyebrow">LIVE OBSERVABILITY</p><h2>客户端与服务端实时运行流</h2><p>两个窗口独立保持连接；客户端记录保留 {sources?.limits.retention_days ?? "—"} 天。</p></div>
      <div className="dual-live-badge"><i /><span>双流实时跟随</span></div>
    </div>

    <div className="log-global-toolbar">
      <label className="log-search"><span className="sr-only">搜索全部日志</span><input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="同时搜索客户端与服务端消息、分类或上下文…" /></label>
      <div className="level-filters" aria-label="全部窗口日志级别筛选">
        {levels.map((level) => <button className={enabledLevels.has(level) ? `level-chip ${level} active` : `level-chip ${level}`} aria-pressed={enabledLevels.has(level)} onClick={() => toggleLevel(level)} key={level}><i />{levelLabels[level]}</button>)}
      </div>
    </div>

    <div className="log-stream-grid">
      <LogPane
        key={`client:${apiBase}`}
        eyebrow="FLUTTER CLIENT"
        title="客户端运行日志"
        description="异常、接口失败、照片上传与生命周期"
        source="client"
        apiBase={apiBase}
        token={token}
        levels={enabledLevels}
        keyword={keyword}
        onNotice={onNotice}
      />
      <LogPane
        key={`backend:${apiBase}:${backendSource}`}
        eyebrow="SERVER CONTAINER"
        title="服务端运行日志"
        description="Docker 容器 stdout / stderr"
        source={selectedBackend?.available ? `backend:${backendSource}` : null}
        apiBase={apiBase}
        token={token}
        levels={enabledLevels}
        keyword={keyword}
        onNotice={onNotice}
        sourceControl={<label className="pane-source-select"><span className="sr-only">选择服务端日志来源</span><select value={backendSource} onChange={(event) => setBackendSource(event.target.value)}>{sources?.backend.map((source) => <option value={source.id} disabled={!source.available} key={source.id}>{source.label}{source.available ? "" : "（不可用）"}</option>)}</select></label>}
      />
    </div>
  </section>;
}

function LogPane({ eyebrow, title, description, source, apiBase, token, levels: enabledLevels, keyword, onNotice, sourceControl }: {
  eyebrow: string;
  title: string;
  description: string;
  source: string | null;
  apiBase: string;
  token: string;
  levels: ReadonlySet<LogLevel>;
  keyword: string;
  onNotice: (message: string) => void;
  sourceControl?: React.ReactNode;
}) {
  const stream = useRuntimeLogStream({ source, apiBase, token, onNotice });
  const viewportRef = useRef<HTMLDivElement>(null);
  const visibleRows = useMemo(
    () => filterLogEvents(stream.rows, enabledLevels, keyword),
    [stream.rows, enabledLevels, keyword],
  );

  useEffect(() => {
    if (!stream.autoScroll || stream.paused || !viewportRef.current) return;
    viewportRef.current.scrollTo({ top: viewportRef.current.scrollHeight, behavior: "smooth" });
  }, [stream.rows, stream.autoScroll, stream.paused]);

  return <article className="log-pane">
    <header className="log-pane-header">
      <div><p className="eyebrow">{eyebrow}</p><h3>{title}</h3><small>{description}</small></div>
      <div className="pane-head-actions">{sourceControl}<div className={`stream-state ${stream.connection}`} role="status"><i />{stream.paused ? "已暂停显示" : stateLabels[stream.connection]}</div></div>
    </header>
    <div className="pane-toolbar">
      <div className="log-actions">
        <button className={stream.paused ? "primary-button" : "ghost-button"} onClick={stream.togglePause} aria-pressed={stream.paused}>{stream.paused ? `继续${stream.pendingCount ? ` · ${stream.pendingCount}` : ""}` : "暂停"}</button>
        <button className="ghost-button" onClick={stream.clearView}>清空</button>
      </div>
      <label className="auto-scroll"><input type="checkbox" checked={stream.autoScroll} onChange={(event) => stream.setAutoScroll(event.target.checked)} />自动滚动</label>
      <span className="log-count">{visibleRows.length} / {stream.rows.length}{stream.skippedCount ? ` · 跳过 ${stream.skippedCount}` : ""}</span>
    </div>

    {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
    <div className="log-viewport" ref={viewportRef} role="region" tabIndex={0} aria-label={`${title}，可使用方向键滚动`} aria-live={stream.paused ? "off" : "polite"}>
      {visibleRows.map((row) => <article className={`log-row ${row.level}`} key={`${row.source_type}-${row.source}-${row.cursor}-${row.occurred_at}`}>
        <time dateTime={row.occurred_at}>{formatTime(row.occurred_at)}</time>
        <span className="log-level">{row.level.toUpperCase()}</span>
        <span className="log-origin">{row.source}<small>{row.category}</small></span>
        <div className="log-message"><p>{row.message}{row.truncated && <em> 已截断</em>}</p>{Object.keys(row.context || {}).length > 0 && <details><summary>上下文</summary><pre>{JSON.stringify(row.context, null, 2)}</pre></details>}</div>
      </article>)}
      {!visibleRows.length && <div className="log-empty"><span>⌁</span><strong>{stream.connection === "connected" ? "实时连接已建立，等待新事件" : stream.connection === "unavailable" ? "当前日志来源不可用" : "正在建立日志连接"}</strong><small>收到事件后会自动追加，无需刷新页面</small></div>}
    </div>
  </article>;
}

function useRuntimeLogStream({ source, apiBase, token, onNotice }: { source: string | null; apiBase: string; token: string; onNotice: (message: string) => void }) {
  const [rows, setRows] = useState<RuntimeLogEvent[]>([]);
  const [paused, setPaused] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const [connection, setConnection] = useState<ConnectionState>(source ? "idle" : "unavailable");
  const [pendingCount, setPendingCount] = useState(0);
  const [skippedCount, setSkippedCount] = useState(0);
  const pausedRef = useRef(false);
  const pendingRef = useRef(new PauseBuffer(240));
  const cursorRef = useRef<string | null>(null);

  useEffect(() => {
    if (!source) return;
    const controller = new AbortController();
    let retry = 0;

    function accept(event: RuntimeLogEvent) {
      if (event.source_type === "client") cursorRef.current = event.cursor;
      if (pausedRef.current) {
        pendingRef.current.push(event);
        setPendingCount(pendingRef.current.size);
        setSkippedCount(pendingRef.current.skipped);
        return;
      }
      setRows((current) => appendUniqueBounded(current, [event]));
    }

    async function connect() {
      while (!controller.signal.aborted) {
        setConnection(retry ? "reconnecting" : "connecting");
        const isClient = source === "client";
        const path = isClient
          ? `/logs/client/stream?tail=240${cursorRef.current ? `&after=${encodeURIComponent(cursorRef.current)}` : ""}`
          : `/logs/backend/stream?source=${encodeURIComponent(source.slice("backend:".length))}&tail=240`;
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
          const decoder = new TextDecoder();
          const parser = new SseParser();
          while (!controller.signal.aborted) {
            const { done, value } = await reader.read();
            if (done) break;
            const envelopes = parser.push(decoder.decode(value, { stream: true }));
            let sourceEnded = false;
            for (const envelope of envelopes) {
              if (envelope.event === "log" && envelope.data && typeof envelope.data === "object") {
                accept(envelope.data as RuntimeLogEvent);
              } else if (envelope.event === "source_status") {
                setConnection("unavailable");
                sourceEnded = true;
              } else if (envelope.event === "heartbeat" || envelope.event === "metadata") {
                setConnection("connected");
              }
            }
            if (sourceEnded) {
              await reader.cancel();
              break;
            }
          }
        } catch (error) {
          if (controller.signal.aborted || (error as Error).name === "AbortError") return;
          setConnection("reconnecting");
          if (retry === 0) onNotice(error instanceof Error ? error.message : "实时日志连接中断");
        }
        if (controller.signal.aborted) return;
        retry += 1;
        const delay = nextReconnectDelay(retry);
        await new Promise<void>((resolve) => {
          const timer = window.setTimeout(resolve, delay);
          controller.signal.addEventListener("abort", () => { window.clearTimeout(timer); resolve(); }, { once: true });
        });
      }
    }

    void connect();
    return () => controller.abort();
  }, [apiBase, token, source, onNotice]);

  function togglePause() {
    if (pausedRef.current) {
      pausedRef.current = false;
      setPaused(false);
      setRows((current) => appendUniqueBounded(current, pendingRef.current.drain()));
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

  return { rows, paused, autoScroll, setAutoScroll, connection, pendingCount, skippedCount, togglePause, clearView };
}

function formatTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(date);
}
