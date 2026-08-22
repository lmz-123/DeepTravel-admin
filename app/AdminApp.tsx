"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import LogConsole from "./logs/LogConsole.tsx";

type Tab = "dashboard" | "cities" | "routes" | "stops" | "challenges" | "media" | "import" | "logs";
type Kind = "city" | "route" | "stop" | "challenge";
type Data = Record<string, unknown>;
type City = { id: string; slug: string; name: string; subtitle: string; hero_image: string; latitude: number; longitude: number };
type Route = { id: string; city_id: string; city_name?: string; slug: string; title: string; subtitle: string; description: string; duration_minutes: number; distance_km: number; difficulty: string; theme: string; hero_image: string; is_featured: boolean; content_status: string; published_at?: string | null; stop_count: number };
type Stop = { id: string; route_id: string; route_title?: string; position: number; title: string; kicker: string; address: string; latitude: number; longitude: number; arrival_radius_m: number; story_title: string; story_body: string; audio_url?: string | null; image: string; insight: string; has_challenge: boolean };
type Challenge = { id: string; stop_id: string; stop_title?: string; route_title?: string; prompt: string; hint: string; options: string[]; correct_option: number; explanation: string };
type Media = { key: string; storage_path: string; mime_type: string; preview_url: string; updated_at: string };
type Dashboard = { cities: number; routes: number; published_routes: number; stops: number; challenges: number; media: number; journeys: number; missing_challenges: number; recent_routes: Route[] };

const navItems: Array<[Tab, string, string]> = [
  ["dashboard", "01", "总览"], ["cities", "02", "城市"], ["routes", "03", "路线"],
  ["stops", "04", "站点与故事"], ["challenges", "05", "题目"], ["media", "06", "媒体库"], ["import", "07", "批量导入"], ["logs", "08", "运行日志"],
];
const titles: Record<Tab, [string, string]> = {
  dashboard: ["内容总览", "CONTENT OPERATIONS"], cities: ["城市管理", "DESTINATIONS"], routes: ["路线管理", "CURATED ROUTES"],
  stops: ["站点与故事", "STORIES & PLACES"], challenges: ["问题管理", "CHALLENGES"], media: ["媒体资源", "MEDIA LIBRARY"], import: ["批量导入", "CONTENT IMPORT"], logs: ["运行日志", "RUNTIME OBSERVABILITY"],
};
const emptyDashboard: Dashboard = { cities: 0, routes: 0, published_routes: 0, stops: 0, challenges: 0, media: 0, journeys: 0, missing_challenges: 0, recent_routes: [] };

export default function AdminApp() {
  const [active, setActive] = useState<Tab>("dashboard");
  const [apiBase, setApiBase] = useState("");
  const [token, setToken] = useState("");
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [editor, setEditor] = useState<{ kind: Kind; item?: Data } | null>(null);
  const [dashboard, setDashboard] = useState<Dashboard>(emptyDashboard);
  const [cities, setCities] = useState<City[]>([]);
  const [routes, setRoutes] = useState<Route[]>([]);
  const [stops, setStops] = useState<Stop[]>([]);
  const [challenges, setChallenges] = useState<Challenge[]>([]);
  const [media, setMedia] = useState<Media[]>([]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setApiBase(localStorage.getItem("jiandi-admin-api") || `${window.location.protocol}//${window.location.hostname}:5100/api/admin`);
      setToken(localStorage.getItem("jiandi-admin-token") || "");
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const request = useCallback(async <T,>(path: string, init: RequestInit = {}, override?: { base: string; token: string }): Promise<T> => {
    const base = (override?.base || apiBase).replace(/\/$/, "");
    const headers = new Headers(init.headers);
    headers.set("Authorization", `Bearer ${override?.token ?? token}`);
    if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
    const response = await fetch(`${base}${path}`, { ...init, headers });
    if (!response.ok) {
      const body = await response.json().catch(() => ({ detail: `请求失败 (${response.status})` }));
      const detail = Array.isArray(body.detail) ? body.detail.map((x: { msg?: string }) => x.msg).join("；") : body.detail;
      throw new Error(detail || `请求失败 (${response.status})`);
    }
    return response.status === 204 ? (undefined as T) : response.json();
  }, [apiBase, token]);

  const loadAll = useCallback(async (override?: { base: string; token: string }) => {
    setLoading(true);
    try {
      await request("/health", {}, override);
      const values = await Promise.all([
        request<Dashboard>("/dashboard", {}, override), request<City[]>("/cities", {}, override), request<Route[]>("/routes", {}, override),
        request<Stop[]>("/stops", {}, override), request<Challenge[]>("/challenges", {}, override), request<Media[]>("/media", {}, override),
      ]);
      setDashboard(values[0]); setCities(values[1]); setRoutes(values[2]); setStops(values[3]); setChallenges(values[4]); setMedia(values[5]);
      setConnected(true); setSettingsOpen(false); return true;
    } catch (error) {
      setConnected(false); setNotice(error instanceof Error ? error.message : "无法连接数据服务"); return false;
    } finally { setLoading(false); }
  }, [request]);

  useEffect(() => { if (!apiBase || !token) return; const timer = window.setTimeout(() => void loadAll(), 0); return () => window.clearTimeout(timer); }, [apiBase, token, loadAll]);
  useEffect(() => { if (!notice) return; const timer = window.setTimeout(() => setNotice(""), 4200); return () => window.clearTimeout(timer); }, [notice]);

  async function saveConnection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    const nextBase = String(form.get("apiBase") || "").trim(); const nextToken = String(form.get("token") || "").trim();
    if (!nextBase || !nextToken) return setNotice("请填写数据服务地址和管理令牌");
    if (await loadAll({ base: nextBase, token: nextToken })) {
      localStorage.setItem("jiandi-admin-api", nextBase); localStorage.setItem("jiandi-admin-token", nextToken);
      setApiBase(nextBase); setToken(nextToken); setNotice("连接成功，内容已同步");
    }
  }
  async function refresh(message?: string) { await loadAll(); if (message) setNotice(message); }
  async function remove(kind: Kind | "media", id: string, label: string) {
    if (!window.confirm(`确定删除“${label}”吗？此操作不可撤销。`)) return;
    const endpoint = kind === "city" ? "cities" : kind === "route" ? "routes" : kind === "stop" ? "stops" : kind === "challenge" ? "challenges" : "media";
    try { await request(`/${endpoint}/${encodeURIComponent(id)}`, { method: "DELETE" }); await refresh("已删除"); }
    catch (error) { setNotice(error instanceof Error ? error.message : "删除失败"); }
  }
  function switchAndCreate(tab: Tab, kind: Kind) { setActive(tab); setEditor({ kind }); }

  return <main className="admin-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">简</span><div><strong>简地</strong><small>内容中台</small></div></div>
      <nav className="side-nav" aria-label="内容管理">{navItems.map(([key, number, label]) => <button className={active === key ? "nav-item active" : "nav-item"} key={key} onClick={() => setActive(key)}><span>{number}</span>{label}</button>)}</nav>
      <button className="connection-card" onClick={() => setSettingsOpen(true)}><i className={connected ? "status-dot" : "status-dot offline"} /><span><strong>{connected ? "服务器已连接" : "服务器未连接"}</strong><small>{connected ? "点击查看连接设置" : "点击配置数据服务"}</small></span></button>
    </aside>
    <section className="workspace">
      <header className="topbar"><div><p className="eyebrow">{titles[active][1]}</p><h1>{titles[active][0]}</h1></div><div className="top-actions">
        <button className="ghost-button" onClick={() => setSettingsOpen(true)}>连接设置</button>
        {active !== "import" && active !== "logs" && <button className="ghost-button" onClick={() => setActive("import")}>导入内容</button>}
        {active === "cities" && <button className="primary-button" onClick={() => setEditor({ kind: "city" })}>＋ 新建城市</button>}
        {(active === "dashboard" || active === "routes") && <button className="primary-button" onClick={() => switchAndCreate("routes", "route")}>＋ 新建路线</button>}
        {active === "stops" && <button className="primary-button" onClick={() => setEditor({ kind: "stop" })}>＋ 新建故事</button>}
        {active === "challenges" && <button className="primary-button" onClick={() => setEditor({ kind: "challenge" })}>＋ 新建问题</button>}
      </div></header>
      {!connected ? <EmptyConnection onOpen={() => setSettingsOpen(true)} /> : <>
        {active === "dashboard" && <DashboardView data={dashboard} onCreate={switchAndCreate} onNavigate={setActive} />}
        {active === "cities" && <CitiesView rows={cities} routes={routes} onEdit={(item) => setEditor({ kind: "city", item })} onDelete={(item) => remove("city", item.id, item.name)} />}
        {active === "routes" && <RoutesView rows={routes} onEdit={(item) => setEditor({ kind: "route", item })} onDelete={(item) => remove("route", item.id, item.title)} />}
        {active === "stops" && <StopsView rows={stops} onEdit={(item) => setEditor({ kind: "stop", item })} onDelete={(item) => remove("stop", item.id, item.title)} />}
        {active === "challenges" && <ChallengesView rows={challenges} onEdit={(item) => setEditor({ kind: "challenge", item })} onDelete={(item) => remove("challenge", item.id, item.prompt)} />}
        {active === "media" && <MediaView rows={media} request={request} onChanged={() => refresh("媒体库已更新")} onDelete={(item) => remove("media", item.key, item.key)} setNotice={setNotice} />}
        {active === "import" && <ImportView request={request} onImported={() => refresh("导入完成，内容已写入数据库")} setNotice={setNotice} />}
        {active === "logs" && <LogConsole apiBase={apiBase} token={token} onNotice={setNotice} />}
      </>}
    </section>
    {(settingsOpen || (!connected && apiBase && !token)) && <ConnectionDialog apiBase={apiBase} token={token} loading={loading} onSubmit={saveConnection} onClose={connected ? () => setSettingsOpen(false) : undefined} />}
    {editor && <EditorDialog editor={editor} cities={cities} routes={routes} stops={stops} media={media} request={request} onClose={() => setEditor(null)} onSaved={() => { setEditor(null); void refresh("内容已保存"); }} setNotice={setNotice} />}
    {loading && <div className="loading-bar" />}{notice && <div className="toast" role="status">{notice}</div>}
  </main>;
}

function EmptyConnection({ onOpen }: { onOpen: () => void }) { return <section className="empty-state"><span>连</span><h2>连接内容数据库</h2><p>配置独立数据服务地址后，即可管理服务器中的城市、路线、故事、问题和媒体资源。</p><button className="primary-button" onClick={onOpen}>配置连接</button></section>; }

function DashboardView({ data, onCreate, onNavigate }: { data: Dashboard; onCreate: (tab: Tab, kind: Kind) => void; onNavigate: (tab: Tab) => void }) {
  return <><section className="stats-grid"><article className="stat-card feature"><span>已上线城市</span><strong>{pad(data.cities)}</strong><small>{data.published_routes} 条路线已发布</small></article><article className="stat-card"><span>路线总数</span><strong>{pad(data.routes)}</strong><small><b>{data.published_routes}</b> 条已发布</small></article><article className="stat-card"><span>故事站点</span><strong>{pad(data.stops)}</strong><small>{data.challenges} 道互动问题</small></article><article className="stat-card"><span>待完善内容</span><strong>{pad(data.missing_challenges)}</strong><small>尚未配置问题的站点</small></article></section>
    <section className="content-grid"><article className="panel routes-panel"><div className="panel-heading"><div><p className="eyebrow">RECENT CONTENT</p><h2>路线内容</h2></div><button className="text-button" onClick={() => onNavigate("routes")}>查看全部 →</button></div><div className="route-table"><div className="table-head"><span>路线</span><span>站点</span><span>状态</span><span>城市</span></div>{data.recent_routes.length ? data.recent_routes.map(route => <div className="table-row" key={route.id}><span className="route-name"><i>{(route.city_name || "城").slice(0, 1)}</i><span><strong>{route.title}</strong><small>{route.theme}</small></span></span><span>{route.stop_count}</span><span><StatusTag status={route.content_status} /></span><span className="muted">{route.city_name}</span></div>) : <TableEmpty text="还没有路线内容" />}</div></article>
      <aside className="panel quick-panel"><div className="panel-heading"><div><p className="eyebrow">QUICK START</p><h2>快速创建</h2></div></div><Quick label="增加城市" help="建立新的内容目的地" icon="城" onClick={() => onCreate("cities", "city")} /><Quick label="增加故事" help="为路线补充站点内容" icon="故" onClick={() => onCreate("stops", "stop")} /><Quick label="增加问题" help="配置选项、答案和解析" icon="问" onClick={() => onCreate("challenges", "challenge")} /><Quick label="上传图片" help="管理路线与故事素材" icon="图" onClick={() => onNavigate("media")} /></aside></section>
    <section className="mini-stats"><span><b>{data.media}</b> 项媒体资源</span><span><b>{data.journeys}</b> 次用户行程</span><span><b>{data.challenges}</b> 道已配置问题</span></section></>;
}

function CitiesView({ rows, routes, onEdit, onDelete }: { rows: City[]; routes: Route[]; onEdit: (x: City) => void; onDelete: (x: City) => void }) { return <ResourcePanel eyebrow="CITY CATALOG" title={`${rows.length} 个城市`}><div className="data-list city-list">{rows.map(item => <article className="data-card" key={item.id}><div className="data-avatar">{item.name.slice(0, 1)}</div><div className="data-main"><h3>{item.name}</h3><p>{item.subtitle}</p><small>{item.latitude.toFixed(4)}, {item.longitude.toFixed(4)} · {routes.filter(x => x.city_id === item.id).length} 条路线</small></div><code>{item.slug}</code><RowActions onEdit={() => onEdit(item)} onDelete={() => onDelete(item)} /></article>)}{!rows.length && <TableEmpty text="还没有城市，先新建一个目的地" />}</div></ResourcePanel>; }
function RoutesView({ rows, onEdit, onDelete }: { rows: Route[]; onEdit: (x: Route) => void; onDelete: (x: Route) => void }) { return <ResourcePanel eyebrow="ROUTE CATALOG" title={`${rows.length} 条路线`}><div className="data-table wide"><div className="data-table-head"><span>路线</span><span>城市</span><span>时长 / 距离</span><span>站点</span><span>状态</span><span /></div>{rows.map(item => <div className="data-table-row" key={item.id}><span><strong>{item.title}</strong><small>{item.theme} · {item.difficulty}</small></span><span>{item.city_name}</span><span>{item.duration_minutes} 分钟 / {item.distance_km} km</span><span>{item.stop_count}</span><span><StatusTag status={item.content_status} /></span><RowActions onEdit={() => onEdit(item)} onDelete={() => onDelete(item)} /></div>)}{!rows.length && <TableEmpty text="还没有路线" />}</div></ResourcePanel>; }
function StopsView({ rows, onEdit, onDelete }: { rows: Stop[]; onEdit: (x: Stop) => void; onDelete: (x: Stop) => void }) { return <ResourcePanel eyebrow="STORY CATALOG" title={`${rows.length} 个故事站点`}><div className="data-list">{rows.map(item => <article className="story-row" key={item.id}><span className="position">{String(item.position).padStart(2, "0")}</span><div className="data-main"><small>{item.route_title}</small><h3>{item.story_title}</h3><p>{item.title} · {item.address}</p></div><span className={item.has_challenge ? "completion yes" : "completion"}>{item.has_challenge ? "已配置问题" : "缺少问题"}</span><RowActions onEdit={() => onEdit(item)} onDelete={() => onDelete(item)} /></article>)}{!rows.length && <TableEmpty text="还没有故事站点" />}</div></ResourcePanel>; }
function ChallengesView({ rows, onEdit, onDelete }: { rows: Challenge[]; onEdit: (x: Challenge) => void; onDelete: (x: Challenge) => void }) { return <ResourcePanel eyebrow="QUESTION BANK" title={`${rows.length} 道互动问题`}><div className="question-grid">{rows.map(item => <article className="question-card" key={item.id}><div className="question-meta"><span>{item.route_title}</span><small>{item.stop_title}</small></div><h3>{item.prompt}</h3><ol>{item.options.map((option, index) => <li className={index === item.correct_option ? "correct" : ""} key={`${index}-${option}`}>{option}</li>)}</ol><div className="question-foot"><small>正确答案：{String.fromCharCode(65 + item.correct_option)}</small><RowActions onEdit={() => onEdit(item)} onDelete={() => onDelete(item)} /></div></article>)}{!rows.length && <TableEmpty text="还没有互动问题" />}</div></ResourcePanel>; }

function MediaView({ rows, request, onChanged, onDelete, setNotice }: { rows: Media[]; request: <T>(p: string, i?: RequestInit) => Promise<T>; onChanged: () => void; onDelete: (x: Media) => void; setNotice: (x: string) => void }) {
  const [uploading, setUploading] = useState(false);
  async function upload(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setUploading(true); try { const body = new FormData(event.currentTarget); await request("/media", { method: "POST", body }); event.currentTarget.reset(); onChanged(); } catch (e) { setNotice(e instanceof Error ? e.message : "上传失败"); } finally { setUploading(false); } }
  function copy(path: string) { void navigator.clipboard.writeText(path); setNotice("资源路径已复制"); }
  return <><section className="upload-panel"><div><p className="eyebrow">UPLOAD ASSET</p><h2>上传图片或音频</h2><p>上传后会写入服务器媒体目录，并在数据库登记资源路径。</p></div><form onSubmit={upload}><label className="file-drop"><input name="file" type="file" accept="image/*,audio/*" required /><span>选择文件</span></label><input name="key" placeholder="资源标识（可选）" /><button className="primary-button" disabled={uploading}>{uploading ? "上传中…" : "上传资源"}</button></form></section><ResourcePanel eyebrow="ASSET LIBRARY" title={`${rows.length} 项媒体资源`}><div className="media-grid">{rows.map(item => <article className="media-card" key={item.key}><div className="media-preview">{item.mime_type.startsWith("image/") ? <img src={item.preview_url} alt="" /> : <span>音频</span>}</div><div><strong>{item.key}</strong><small>{item.storage_path}</small><em>{item.mime_type}</em></div><div className="media-actions"><button onClick={() => copy(item.storage_path)}>复制路径</button><button className="danger-link" onClick={() => onDelete(item)}>删除</button></div></article>)}{!rows.length && <TableEmpty text="还没有媒体资源" />}</div></ResourcePanel></>;
}

function ImportView({ request, onImported, setNotice }: { request: <T>(p: string, i?: RequestInit) => Promise<T>; onImported: () => void; setNotice: (x: string) => void }) {
  const sample = useMemo(() => JSON.stringify({ cities: [{ slug: "hangzhou", name: "杭州", subtitle: "在水岸与街巷之间漫游", hero_image: "images/hangzhou.jpg", latitude: 30.2741, longitude: 120.1551 }], routes: [], stops: [], challenges: [] }, null, 2), []);
  const [content, setContent] = useState(sample); const [importing, setImporting] = useState(false);
  function readFile(event: React.ChangeEvent<HTMLInputElement>) { const file = event.target.files?.[0]; if (!file) return; const reader = new FileReader(); reader.onload = () => setContent(String(reader.result || "")); reader.readAsText(file); }
  async function submit() { setImporting(true); try { await request("/import", { method: "POST", body: JSON.stringify(JSON.parse(content)) }); onImported(); } catch (e) { setNotice(e instanceof Error ? e.message : "导入失败"); } finally { setImporting(false); } }
  return <section className="import-layout"><article className="panel import-editor"><div className="panel-heading"><div><p className="eyebrow">JSON IMPORT</p><h2>内容数据</h2></div><label className="small-upload">读取 JSON<input type="file" accept="application/json,.json" onChange={readFile} /></label></div><textarea value={content} onChange={(e) => setContent(e.target.value)} spellCheck={false} /><div className="import-actions"><button className="ghost-button" onClick={() => setContent(sample)}>恢复示例</button><button className="primary-button" onClick={submit} disabled={importing}>{importing ? "导入中…" : "校验并导入数据库"}</button></div></article><aside className="panel import-help"><p className="eyebrow">SUPPORTED CONTENT</p><h2>支持内容</h2><ul><li><b>cities</b><span>城市与封面信息</span></li><li><b>routes</b><span>路线、发布状态与主题</span></li><li><b>stops</b><span>地点、故事、观察提示</span></li><li><b>challenges</b><span>问题、选项、答案与解析</span></li></ul><p>可使用平铺结构，也可把 stops 嵌套在 routes 中、challenge 嵌套在 stop 中。整批数据在同一事务中写入，任一项错误会整体回滚。</p></aside></section>;
}

function ConnectionDialog({ apiBase, token, loading, onSubmit, onClose }: { apiBase: string; token: string; loading: boolean; onSubmit: (e: FormEvent<HTMLFormElement>) => void; onClose?: () => void }) { return <div className="modal-backdrop"><section className="modal connection-modal" role="dialog" aria-modal="true"><div className="modal-head"><div><p className="eyebrow">DATABASE CONNECTION</p><h2>连接内容数据服务</h2></div>{onClose && <button className="close-button" onClick={onClose}>×</button>}</div><p className="form-intro">管理后台通过独立数据服务读写现有 MySQL。令牌仅保存在当前浏览器。</p><form className="editor-form" onSubmit={onSubmit}><Field label="数据服务地址"><input name="apiBase" defaultValue={apiBase} placeholder="https://admin-api.example.com/api/admin" required /></Field><Field label="管理令牌"><input name="token" type="password" defaultValue={token} required /></Field><button className="primary-button full" disabled={loading}>{loading ? "正在验证…" : "连接并同步内容"}</button></form></section></div>; }

function EditorDialog({ editor, cities, routes, stops, media, request, onClose, onSaved, setNotice }: { editor: { kind: Kind; item?: Data }; cities: City[]; routes: Route[]; stops: Stop[]; media: Media[]; request: <T>(p: string, i?: RequestInit) => Promise<T>; onClose: () => void; onSaved: () => void; setNotice: (x: string) => void }) {
  const [saving, setSaving] = useState(false); const item = editor.item || {}; const editing = Boolean(editor.item);
  const title = `${editing ? "编辑" : "新建"}${editor.kind === "city" ? "城市" : editor.kind === "route" ? "路线" : editor.kind === "stop" ? "故事站点" : "互动问题"}`;
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setSaving(true); const form = new FormData(event.currentTarget); const payload: Data = {}; for (const [key, value] of form.entries()) payload[key] = value;
    if (editor.kind === "city") { payload.latitude = Number(payload.latitude); payload.longitude = Number(payload.longitude); }
    if (editor.kind === "route") { payload.duration_minutes = Number(payload.duration_minutes); payload.distance_km = Number(payload.distance_km); payload.is_featured = form.get("is_featured") === "on"; payload.published_at = payload.published_at || null; }
    if (editor.kind === "stop") { payload.position = Number(payload.position); payload.latitude = Number(payload.latitude); payload.longitude = Number(payload.longitude); payload.arrival_radius_m = Number(payload.arrival_radius_m); payload.audio_url = payload.audio_url || null; }
    if (editor.kind === "challenge") { payload.options = String(payload.options).split("\n").map(x => x.trim()).filter(Boolean); payload.correct_option = Number(payload.correct_option); }
    const endpoint = editor.kind === "city" ? "cities" : editor.kind === "route" ? "routes" : editor.kind === "stop" ? "stops" : "challenges";
    try { await request(`/${endpoint}${editing ? `/${item.id}` : ""}`, { method: editing ? "PUT" : "POST", body: JSON.stringify(payload) }); onSaved(); } catch (e) { setNotice(e instanceof Error ? e.message : "保存失败"); } finally { setSaving(false); }
  }
  return <div className="modal-backdrop"><section className="modal editor-modal" role="dialog" aria-modal="true"><div className="modal-head"><div><p className="eyebrow">CONTENT EDITOR</p><h2>{title}</h2></div><button className="close-button" onClick={onClose}>×</button></div><form className="editor-form" onSubmit={submit}>{editor.kind === "city" && <CityFields item={item} media={media} />}{editor.kind === "route" && <RouteFields item={item} cities={cities} media={media} />}{editor.kind === "stop" && <StopFields item={item} routes={routes} media={media} />}{editor.kind === "challenge" && <ChallengeFields item={item} stops={stops} />}<div className="modal-actions"><button type="button" className="ghost-button" onClick={onClose}>取消</button><button className="primary-button" disabled={saving}>{saving ? "保存中…" : "保存内容"}</button></div></form></section></div>;
}

function CityFields({ item, media }: { item: Data; media: Media[] }) { return <><div className="form-grid"><Field label="城市名称"><input name="name" defaultValue={str(item.name)} required /></Field><Field label="英文标识"><input name="slug" defaultValue={str(item.slug)} placeholder="shanghai" required /></Field></div><Field label="城市副标题"><input name="subtitle" defaultValue={str(item.subtitle)} required /></Field><MediaField name="hero_image" label="城市封面路径" value={str(item.hero_image)} media={media} /><div className="form-grid"><Field label="纬度"><input name="latitude" type="number" step="any" defaultValue={num(item.latitude, 31.2304)} required /></Field><Field label="经度"><input name="longitude" type="number" step="any" defaultValue={num(item.longitude, 121.4737)} required /></Field></div></>; }
function RouteFields({ item, cities, media }: { item: Data; cities: City[]; media: Media[] }) { return <><div className="form-grid"><Field label="所属城市"><select name="city_id" defaultValue={str(item.city_id)} required><option value="">请选择</option>{cities.map(x => <option value={x.id} key={x.id}>{x.name}</option>)}</select></Field><Field label="英文标识"><input name="slug" defaultValue={str(item.slug)} required /></Field></div><Field label="路线标题"><input name="title" defaultValue={str(item.title)} required /></Field><Field label="路线副标题"><input name="subtitle" defaultValue={str(item.subtitle)} required /></Field><Field label="路线介绍"><textarea name="description" defaultValue={str(item.description)} rows={4} required /></Field><div className="form-grid three"><Field label="时长（分钟）"><input name="duration_minutes" type="number" min="1" defaultValue={num(item.duration_minutes, 90)} required /></Field><Field label="距离（公里）"><input name="distance_km" type="number" min="0.1" step="0.1" defaultValue={num(item.distance_km, 2.5)} required /></Field><Field label="难度"><input name="difficulty" defaultValue={str(item.difficulty) || "轻松"} required /></Field></div><div className="form-grid"><Field label="主题"><input name="theme" defaultValue={str(item.theme)} required /></Field><Field label="发布状态"><select name="content_status" defaultValue={str(item.content_status) || "draft"}><option value="draft">草稿</option><option value="review">审核中</option><option value="published">已发布</option><option value="archived">已下线</option></select></Field></div><MediaField name="hero_image" label="路线封面路径" value={str(item.hero_image)} media={media} /><div className="form-grid"><label className="checkbox-field"><input name="is_featured" type="checkbox" defaultChecked={Boolean(item.is_featured)} /><span>设为精选路线</span></label><Field label="发布时间（可选）"><input name="published_at" type="datetime-local" defaultValue={dateInput(item.published_at)} /></Field></div></>; }
function StopFields({ item, routes, media }: { item: Data; routes: Route[]; media: Media[] }) { return <><div className="form-grid"><Field label="所属路线"><select name="route_id" defaultValue={str(item.route_id)} required><option value="">请选择</option>{routes.map(x => <option value={x.id} key={x.id}>{x.city_name} · {x.title}</option>)}</select></Field><Field label="站点顺序"><input name="position" type="number" min="1" defaultValue={num(item.position, 1)} required /></Field></div><div className="form-grid"><Field label="地点名称"><input name="title" defaultValue={str(item.title)} required /></Field><Field label="引导短句"><input name="kicker" defaultValue={str(item.kicker)} required /></Field></div><Field label="地址"><input name="address" defaultValue={str(item.address)} required /></Field><div className="form-grid three"><Field label="纬度"><input name="latitude" type="number" step="any" defaultValue={num(item.latitude, 31.2304)} required /></Field><Field label="经度"><input name="longitude" type="number" step="any" defaultValue={num(item.longitude, 121.4737)} required /></Field><Field label="到达半径（米）"><input name="arrival_radius_m" type="number" min="1" defaultValue={num(item.arrival_radius_m, 80)} required /></Field></div><Field label="故事标题"><input name="story_title" defaultValue={str(item.story_title)} required /></Field><Field label="故事正文"><textarea name="story_body" defaultValue={str(item.story_body)} rows={7} required /></Field><Field label="观察洞见"><textarea name="insight" defaultValue={str(item.insight)} rows={3} required /></Field><MediaField name="image" label="故事图片路径" value={str(item.image)} media={media} /><MediaField name="audio_url" label="音频路径（可选）" value={str(item.audio_url)} media={media.filter(x => x.mime_type.startsWith("audio/"))} /></>; }
function ChallengeFields({ item, stops }: { item: Data; stops: Stop[] }) { const options = Array.isArray(item.options) ? item.options.join("\n") : ""; return <><Field label="所属站点"><select name="stop_id" defaultValue={str(item.stop_id)} required><option value="">请选择</option>{stops.map(x => <option value={x.id} key={x.id}>{x.route_title} · {x.position}. {x.title}</option>)}</select></Field><Field label="问题"><textarea name="prompt" defaultValue={str(item.prompt)} rows={3} required /></Field><Field label="提示"><textarea name="hint" defaultValue={str(item.hint)} rows={2} required /></Field><Field label="选项（每行一个）"><textarea name="options" defaultValue={options} rows={5} placeholder={"选项 A\n选项 B\n选项 C"} required /></Field><Field label="正确答案序号（第一个选项为 0）"><input name="correct_option" type="number" min="0" defaultValue={num(item.correct_option, 0)} required /></Field><Field label="答案解析"><textarea name="explanation" defaultValue={str(item.explanation)} rows={3} required /></Field></>; }

function ResourcePanel({ eyebrow, title, children }: { eyebrow: string; title: string; children: React.ReactNode }) { return <section className="panel resource-panel"><div className="panel-heading"><div><p className="eyebrow">{eyebrow}</p><h2>{title}</h2></div></div>{children}</section>; }
function Field({ label, children }: { label: string; children: React.ReactNode }) { return <label className="field"><span>{label}</span>{children}</label>; }
function MediaField({ name, label, value, media }: { name: string; label: string; value: string; media: Media[] }) { const listId = `media-${name}`; return <Field label={label}><input name={name} defaultValue={value} list={listId} required={name !== "audio_url"} /><datalist id={listId}>{media.map(x => <option value={x.storage_path} key={x.key}>{x.key}</option>)}</datalist></Field>; }
function RowActions({ onEdit, onDelete }: { onEdit: () => void; onDelete: () => void }) { return <span className="row-actions"><button onClick={onEdit}>编辑</button><button className="danger-link" onClick={onDelete}>删除</button></span>; }
function Quick({ label, help, icon, onClick }: { label: string; help: string; icon: string; onClick: () => void }) { return <button className="quick-action" onClick={onClick}><span>{icon}</span><div><strong>{label}</strong><small>{help}</small></div><b>＋</b></button>; }
function StatusTag({ status }: { status: string }) { const label: Record<string, string> = { published: "已发布", draft: "草稿", review: "审核中", archived: "已下线", demo_unverified: "待审核" }; return <em className={`tag ${status === "published" ? "published" : ""}`}>{label[status] || status}</em>; }
function TableEmpty({ text }: { text: string }) { return <div className="table-empty">{text}</div>; }
function pad(value: number) { return String(value).padStart(2, "0"); }
function str(value: unknown) { return value == null ? "" : String(value); }
function num(value: unknown, fallback: number) { return value == null || value === "" ? fallback : Number(value); }
function dateInput(value: unknown) { return value ? String(value).slice(0, 16) : ""; }
