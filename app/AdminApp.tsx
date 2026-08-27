"use client";
/* eslint-disable @next/next/no-img-element -- CMS renders operator-provided OSS/CDN URLs without a fixed image loader. */

import {
  FormEvent,
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import LogConsole from "./logs/LogConsole.tsx";

type Tab =
  | "dashboard"
  | "cities"
  | "scenic"
  | "catalog"
  | "media"
  | "import"
  | "logs";
type Kind = "city" | "route" | "stop";
type Data = Record<string, unknown>;
type City = {
  id: string;
  slug: string;
  name: string;
  subtitle: string;
  hero_image: string;
  latitude: number;
  longitude: number;
};
type Route = {
  id: string;
  city_id: string;
  city_name?: string;
  slug: string;
  title: string;
  subtitle: string;
  description: string;
  duration_minutes: number;
  distance_km: number;
  difficulty: string;
  theme: string;
  hero_image: string;
  is_featured: boolean;
  content_status: string;
  published_at?: string | null;
  stop_count: number;
};
type Stop = {
  id: string;
  route_id: string;
  route_title?: string;
  position: number;
  title: string;
  kicker: string;
  address: string;
  latitude: number;
  longitude: number;
  arrival_radius_m: number;
  story_title: string;
  story_body: string;
  audio_url?: string | null;
  image: string;
  insight: string;
  experience_tags: string[];
  has_challenge: boolean;
};
type Media = {
  key: string;
  storage_path: string;
  mime_type: string;
  preview_url: string;
  updated_at: string;
  storage_provider?: string;
  object_key?: string;
  canonical_url?: string;
  size_bytes?: number;
  checksum_sha256?: string;
};
type MediaHierarchy = {
  cities: Array<{ id: string; name: string; scenics: Array<{ id: string; title: string; status: string; assets: string[] }> }>;
  assets: Record<string, { key: string; object_key: string; mime_type: string; size_bytes?: number; checksum_sha256?: string; scope: string; delivery: string; reference_count: number; usages: Array<{ role: string }> }>;
  unassigned: string[];
  readiness: { ready: boolean; cdn_base: string; public_count: number; private_count: number; canonical_resource_set: string; blockers: string[] };
};
type Dashboard = {
  cities: number;
  routes: number;
  published_routes: number;
  stops: number;
  challenges: number;
  media: number;
  journeys: number;
  missing_challenges: number;
  recent_routes: Route[];
};
type ValidationIssue = { path: string; code: string; message: string };
type GraphValidation = {
  valid: boolean;
  errors: ValidationIssue[];
  warnings: ValidationIssue[];
};
type RouteGraph = {
  package_id?: string | null;
  package_version?: string | null;
  route: Data;
  story_arc: Data | null;
  fragments: Data[];
  sources: Data[];
  claims: Data[];
  required_photo_mission_count: number;
};
type NarrationPreviewView = {
  id: string;
  status: string;
  error_code?: string | null;
  provider: string;
  model: string;
  voice_id: string;
  emotion: string;
  speed: number;
  pitch: number;
  playback_path?: string | null;
  metadata: Data;
};
type NarrationProfileView = {
  id: string;
  slug: string;
  display_name: string;
  description: string;
  provider: string;
  model: string;
  voice_id: string;
  emotion: string;
  speed: number;
  pitch: number;
  preview_media_path?: string | null;
  display_order: number;
  status: string;
  is_default: boolean;
  published_at?: string | null;
};
type NarrationCoverage = {
  route_id: string;
  profile_id: string;
  total: number;
  complete_count: number;
  complete_fragment_ids: string[];
  missing: Array<{ id: string; title: string }>;
  stale: Array<{ id: string; title: string }>;
  ready: boolean;
};
type NarrationVariant = {
  label: string;
  emotion: string;
  speed: number;
  pitch: number;
};
type NarrationConfigView = {
  provider: string;
  model: string;
  default_voice_id: string;
  credentials_configured: boolean;
  supported_emotions: string[];
  presets: NarrationVariant[];
};
type NarrationBatchResult = {
  route_id: string;
  profile: NarrationProfileView;
  generated_count: number;
  failed_count: number;
  skipped_count: number;
  coverage: NarrationCoverage;
  results: Array<{
    fragment_id: string;
    title: string;
    status: "saved" | "failed" | "skipped";
    error_code?: string;
    media_path?: string;
  }>;
};
type HomeStoryTrackView = {
  id: string;
  profile_id: string;
  profile_name: string;
  status: string;
  duration_ms: number;
  is_current: boolean;
  playback_path: string;
};
type HomeStoryView = {
  arc_id: string;
  arc_title: string;
  route_title: string;
  route_status: string;
  city_name: string;
  transcript: string;
  transcript_hash: string;
  script_version: string;
  publication: {
    id: string;
    title: string;
    introduction: string;
    cover_image: string;
    selection_weight: number;
    status: string;
    selected_track_id?: string | null;
  } | null;
  tracks: HomeStoryTrackView[];
  blockers: string[];
  ready_to_publish: boolean;
};
type StoryCatalogView = {
  id: string;
  city_id: string;
  source_kind: string;
  source_id: string;
  title: string;
  summary: string;
  cover_image: string;
  district?: string | null;
  themes: string[];
  point_ids: string[];
  related_stories: Data[];
  content_type: string;
  place_context: string;
  observable_detail: string;
  attention_hint?: string | null;
  sources: Data[];
  fact_status: string;
  review_status: string;
  status: string;
  version: number;
  source: Data;
  story_content: string;
  variants: Data[];
  placements: Data[];
  warnings: string[];
  blockers: string[];
  ready_to_publish: boolean;
};
type ImportPreview = {
  preview_id: string;
  confirmation_token?: string | null;
  expires_at: string;
  counts: Record<string, number>;
  changes: Array<{
    entity: string;
    id: string;
    status: string;
    path: string;
    changed_fields: string[];
    problems: ValidationIssue[];
  }>;
  problems: ValidationIssue[];
  can_confirm: boolean;
};

const navItems: Array<[Tab, string, string]> = [
  ["dashboard", "01", "总览"],
  ["cities", "02", "城市"],
  ["scenic", "03", "景点内容"],
  ["catalog", "04", "城市故事"],
  ["media", "05", "媒体库"],
  ["import", "06", "批量导入"],
  ["logs", "07", "运行日志"],
];
const titles: Record<Tab, [string, string]> = {
  dashboard: ["内容总览", "CONTENT OPERATIONS"],
  cities: ["城市管理", "DESTINATIONS"],
  scenic: ["景点内容", "SCENIC CONTENT"],
  catalog: ["城市故事", "CITY STORIES"],
  media: ["媒体资源", "MEDIA LIBRARY"],
  import: ["批量导入", "CONTENT IMPORT"],
  logs: ["运行日志", "RUNTIME OBSERVABILITY"],
};
const emptyDashboard: Dashboard = {
  cities: 0,
  routes: 0,
  published_routes: 0,
  stops: 0,
  challenges: 0,
  media: 0,
  journeys: 0,
  missing_challenges: 0,
  recent_routes: [],
};

export default function AdminApp() {
  const [active, setActive] = useState<Tab>("dashboard");
  const [apiBase, setApiBase] = useState("");
  const [token, setToken] = useState("");
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [editor, setEditor] = useState<{ kind: Kind; item?: Data } | null>(
    null,
  );
  const [dashboard, setDashboard] = useState<Dashboard>(emptyDashboard);
  const [cities, setCities] = useState<City[]>([]);
  const [routes, setRoutes] = useState<Route[]>([]);
  const [stops, setStops] = useState<Stop[]>([]);
  const [media, setMedia] = useState<Media[]>([]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setApiBase(
        localStorage.getItem("jiandi-admin-api") ||
          `${window.location.protocol}//${window.location.hostname}:5100/api/admin`,
      );
      setToken(localStorage.getItem("jiandi-admin-token") || "");
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const request = useCallback(
    async <T,>(
      path: string,
      init: RequestInit = {},
      override?: { base: string; token: string },
    ): Promise<T> => {
      const base = (override?.base || apiBase).replace(/\/$/, "");
      const headers = new Headers(init.headers);
      headers.set("Authorization", `Bearer ${override?.token ?? token}`);
      if (init.body && !(init.body instanceof FormData))
        headers.set("Content-Type", "application/json");
      const response = await fetch(`${base}${path}`, { ...init, headers });
      if (!response.ok) {
        const body = await response
          .json()
          .catch(() => ({ detail: `请求失败 (${response.status})` }));
        const detail = Array.isArray(body.detail)
          ? body.detail.map((x: { msg?: string }) => x.msg).join("；")
          : typeof body.detail === "object" && body.detail
            ? body.detail.message || JSON.stringify(body.detail)
            : body.detail;
        throw new Error(detail || `请求失败 (${response.status})`);
      }
      if (response.status === 204) return undefined as T;
      if ((response.headers.get("content-type") || "").startsWith("audio/"))
        return (await response.arrayBuffer()) as T;
      return response.json();
    },
    [apiBase, token],
  );

  const loadAll = useCallback(
    async (override?: { base: string; token: string }) => {
      setLoading(true);
      try {
        await request("/health", {}, override);
        const values = await Promise.all([
          request<Dashboard>("/dashboard", {}, override),
          request<City[]>("/cities", {}, override),
          request<Route[]>("/routes", {}, override),
          request<Stop[]>("/stops", {}, override),
          request<Media[]>("/media", {}, override),
        ]);
        setDashboard(values[0]);
        setCities(values[1]);
        setRoutes(values[2]);
        setStops(values[3]);
        setMedia(values[4]);
        setConnected(true);
        setSettingsOpen(false);
        return true;
      } catch (error) {
        setConnected(false);
        setNotice(error instanceof Error ? error.message : "无法连接数据服务");
        return false;
      } finally {
        setLoading(false);
      }
    },
    [request],
  );

  useEffect(() => {
    if (!apiBase || !token) return;
    const timer = window.setTimeout(() => void loadAll(), 0);
    return () => window.clearTimeout(timer);
  }, [apiBase, token, loadAll]);
  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 4200);
    return () => window.clearTimeout(timer);
  }, [notice]);

  async function saveConnection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const nextBase = String(form.get("apiBase") || "").trim();
    const nextToken = String(form.get("token") || "").trim();
    if (!nextBase || !nextToken)
      return setNotice("请填写数据服务地址和管理令牌");
    if (await loadAll({ base: nextBase, token: nextToken })) {
      localStorage.setItem("jiandi-admin-api", nextBase);
      localStorage.setItem("jiandi-admin-token", nextToken);
      setApiBase(nextBase);
      setToken(nextToken);
      setNotice("连接成功，内容已同步");
    }
  }
  async function refresh(message?: string) {
    await loadAll();
    if (message) setNotice(message);
  }
  // Kept temporarily for rollback compatibility; route lifecycle is now operated inside 景点内容.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  async function transitionRoute(item: Route) {
    const transition: Record<
      string,
      { endpoint: string; label: string; done: string }
    > = {
      draft: {
        endpoint: "submit-review",
        label: "提交审核",
        done: "路线已提交审核",
      },
      in_review: {
        endpoint: "verify",
        label: "通过审核",
        done: "路线已审核，尚未发布",
      },
      verified: {
        endpoint: "publish",
        label: "发布上线",
        done: "路线已发布到客户端",
      },
      published: {
        endpoint: "archive",
        label: "归档下线",
        done: "路线已归档；既有行程仍可继续",
      },
    };
    const action = transition[item.content_status];
    if (!action) return;
    if (
      (item.content_status === "published" ||
        item.content_status === "verified") &&
      !window.confirm(`确认${action.label}“${item.title}”？`)
    )
      return;
    try {
      await request(`/routes/${item.id}/${action.endpoint}`, {
        method: "POST",
      });
      await refresh(action.done);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : `${action.label}失败`);
    }
  }
  async function remove(kind: Kind | "media", id: string, label: string) {
    if (!window.confirm(`确定删除“${label}”吗？此操作不可撤销。`)) return;
    const endpoint =
      kind === "city"
        ? "cities"
        : kind === "route"
          ? "routes"
          : kind === "stop"
            ? "stops"
            : "media";
    try {
      await request(`/${endpoint}/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      await refresh("已删除");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "删除失败");
    }
  }
  function switchAndCreate(tab: Tab, kind: Kind) {
    setActive(tab);
    setEditor({ kind });
  }

  return (
    <main className="admin-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">简</span>
          <div>
            <strong>简地</strong>
            <small>内容中台</small>
          </div>
        </div>
        <nav className="side-nav" aria-label="内容管理">
          {navItems.map(([key, number, label]) => (
            <button
              className={active === key ? "nav-item active" : "nav-item"}
              key={key}
              onClick={() => setActive(key)}
            >
              <span>{number}</span>
              {label}
            </button>
          ))}
        </nav>
        <button
          className="connection-card"
          onClick={() => setSettingsOpen(true)}
        >
          <i className={connected ? "status-dot" : "status-dot offline"} />
          <span>
            <strong>{connected ? "服务器已连接" : "服务器未连接"}</strong>
            <small>{connected ? "点击查看连接设置" : "点击配置数据服务"}</small>
          </span>
        </button>
      </aside>
      <section className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">{titles[active][1]}</p>
            <h1>{titles[active][0]}</h1>
          </div>
          <div className="top-actions">
            <button
              className="ghost-button"
              onClick={() => setSettingsOpen(true)}
            >
              连接设置
            </button>
            {active !== "import" && active !== "logs" && (
              <button
                className="ghost-button"
                onClick={() => setActive("import")}
              >
                导入内容
              </button>
            )}
            {active === "cities" && (
              <button
                className="primary-button"
                onClick={() => setEditor({ kind: "city" })}
              >
                ＋ 新建城市
              </button>
            )}
            {active === "dashboard" && (
              <button
                className="primary-button"
                onClick={() => switchAndCreate("scenic", "route")}
              >
                ＋ 新建景点
              </button>
            )}
            {active === "scenic" && (
              <>
                <button className="ghost-button" onClick={() => setEditor({ kind: "route" })}>
                  ＋ 新建景点
                </button>
                <button className="primary-button" onClick={() => setEditor({ kind: "stop" })}>
                  ＋ 新建节点
                </button>
              </>
            )}
          </div>
        </header>
        {!connected ? (
          <EmptyConnection onOpen={() => setSettingsOpen(true)} />
        ) : (
          <>
            {active === "dashboard" && (
              <DashboardView
                data={dashboard}
                onCreate={switchAndCreate}
                onNavigate={setActive}
              />
            )}
            {active === "cities" && (
              <CitiesView
                rows={cities}
                routes={routes}
                onEdit={(item) => setEditor({ kind: "city", item })}
                onDelete={(item) => remove("city", item.id, item.name)}
              />
            )}
            {active === "scenic" && (
              <ScenicContentWorkspace
                routes={routes}
                stops={stops}
                request={request}
                setNotice={setNotice}
                onChanged={() => refresh()}
                onEditScenic={(item) => setEditor({ kind: "route", item })}
                onDeleteStop={(item) => remove("stop", item.id, item.title)}
              />
            )}
            {active === "catalog" && (
              <CityStoryCatalogWorkspace
                cities={cities}
                request={request}
                setNotice={setNotice}
              />
            )}
            {active === "media" && (
              <MediaView
                rows={media}
                request={request}
                onChanged={() => refresh("媒体库已更新")}
                onDelete={(item) => remove("media", item.key, item.key)}
                setNotice={setNotice}
              />
            )}
            {active === "import" && (
              <ImportView
                request={request}
                onImported={() => refresh("导入完成，内容已写入数据库")}
                setNotice={setNotice}
              />
            )}
            {active === "logs" && (
              <LogConsole
                apiBase={apiBase}
                token={token}
                onNotice={setNotice}
              />
            )}
          </>
        )}
      </section>
      {(settingsOpen || (!connected && apiBase && !token)) && (
        <ConnectionDialog
          apiBase={apiBase}
          token={token}
          loading={loading}
          onSubmit={saveConnection}
          onClose={connected ? () => setSettingsOpen(false) : undefined}
        />
      )}
      {editor && (
        <EditorDialog
          editor={editor}
          cities={cities}
          routes={routes}
          media={media}
          request={request}
          onClose={() => setEditor(null)}
          onSaved={() => {
            setEditor(null);
            void refresh("内容已保存");
          }}
          setNotice={setNotice}
        />
      )}
      {loading && <div className="loading-bar" />}
      {notice && (
        <div className="toast" role="status">
          {notice}
        </div>
      )}
    </main>
  );
}

function EmptyConnection({ onOpen }: { onOpen: () => void }) {
  return (
    <section className="empty-state">
      <span>连</span>
      <h2>连接内容数据库</h2>
      <p>
        配置独立数据服务地址后，即可管理城市、景点、故事和 OSS 媒体资源。
      </p>
      <button className="primary-button" onClick={onOpen}>
        配置连接
      </button>
    </section>
  );
}

function DashboardView({
  data,
  onCreate,
  onNavigate,
}: {
  data: Dashboard;
  onCreate: (tab: Tab, kind: Kind) => void;
  onNavigate: (tab: Tab) => void;
}) {
  return (
    <>
      <section className="stats-grid">
        <article className="stat-card feature">
          <span>已上线城市</span>
          <strong>{pad(data.cities)}</strong>
          <small>{data.published_routes} 个景点已发布</small>
        </article>
        <article className="stat-card">
          <span>景点总数</span>
          <strong>{pad(data.routes)}</strong>
          <small>
            <b>{data.published_routes}</b> 条已发布
          </small>
        </article>
        <article className="stat-card">
          <span>内容节点</span>
          <strong>{pad(data.stops)}</strong>
          <small>可配置文案、定位与标签</small>
        </article>
        <article className="stat-card">
          <span>媒体资源</span>
          <strong>{pad(data.media)}</strong>
          <small>全部持久化到 OSS</small>
        </article>
      </section>
      <section className="content-grid">
        <article className="panel routes-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">RECENT CONTENT</p>
              <h2>最近景点</h2>
            </div>
            <button
              className="text-button"
              onClick={() => onNavigate("scenic")}
            >
              查看全部 →
            </button>
          </div>
          <div className="route-table">
            <div className="table-head">
              <span>景点</span>
              <span>节点</span>
              <span>状态</span>
              <span>城市</span>
            </div>
            {data.recent_routes.length ? (
              data.recent_routes.map((route) => (
                <div className="table-row" key={route.id}>
                  <span className="route-name">
                    <i>{(route.city_name || "城").slice(0, 1)}</i>
                    <span>
                      <strong>{route.title}</strong>
                      <small>{route.theme}</small>
                    </span>
                  </span>
                  <span>{route.stop_count}</span>
                  <span>
                    <StatusTag status={route.content_status} />
                  </span>
                  <span className="muted">{route.city_name}</span>
                </div>
              ))
            ) : (
              <TableEmpty text="还没有景点内容" />
            )}
          </div>
        </article>
        <aside className="panel quick-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">QUICK START</p>
              <h2>快速创建</h2>
            </div>
          </div>
          <Quick
            label="增加城市"
            help="建立新的内容目的地"
            icon="城"
            onClick={() => onCreate("cities", "city")}
          />
          <Quick
            label="增加节点"
            help="为景点补充文案与位置"
            icon="故"
            onClick={() => onCreate("scenic", "stop")}
          />
          <Quick
            label="增加景点"
            help="建立新的景点内容"
            icon="景"
            onClick={() => onCreate("scenic", "route")}
          />
          <Quick
            label="上传图片"
            help="管理景点与故事素材"
            icon="图"
            onClick={() => onNavigate("media")}
          />
        </aside>
      </section>
      <section className="mini-stats">
        <span>
          <b>{data.media}</b> 项媒体资源
        </span>
        <span>
          <b>{data.journeys}</b> 次用户行程
        </span>
        <span><b>{data.routes}</b> 个景点内容</span>
      </section>
    </>
  );
}

function CitiesView({
  rows,
  routes,
  onEdit,
  onDelete,
}: {
  rows: City[];
  routes: Route[];
  onEdit: (x: City) => void;
  onDelete: (x: City) => void;
}) {
  return (
    <ResourcePanel eyebrow="CITY CATALOG" title={`${rows.length} 个城市`}>
      <div className="data-list city-list">
        {rows.map((item) => (
          <article className="data-card" key={item.id}>
            <div className="data-avatar">{item.name.slice(0, 1)}</div>
            <div className="data-main">
              <h3>{item.name}</h3>
              <p>{item.subtitle}</p>
              <small>
                {item.latitude.toFixed(4)}, {item.longitude.toFixed(4)} ·{" "}
                {routes.filter((x) => x.city_id === item.id).length} 条路线
              </small>
            </div>
            <code>{item.slug}</code>
            <RowActions
              onEdit={() => onEdit(item)}
              onDelete={() => onDelete(item)}
            />
          </article>
        ))}
        {!rows.length && <TableEmpty text="还没有城市，先新建一个目的地" />}
      </div>
    </ResourcePanel>
  );
}
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function RoutesView({
  rows,
  onEdit,
  onDelete,
  onTransition,
}: {
  rows: Route[];
  onEdit: (x: Route) => void;
  onDelete: (x: Route) => void;
  onTransition: (x: Route) => void;
}) {
  const actions: Record<string, string> = {
    draft: "提交审核",
    in_review: "通过审核",
    verified: "发布上线",
    published: "归档下线",
  };
  return (
    <ResourcePanel eyebrow="ROUTE CATALOG" title={`${rows.length} 条路线`}>
      <div className="data-table wide">
        <div className="data-table-head">
          <span>路线</span>
          <span>城市</span>
          <span>时长 / 距离</span>
          <span>站点</span>
          <span>状态</span>
          <span />
        </div>
        {rows.map((item) => (
          <div className="data-table-row" key={item.id}>
            <span>
              <strong>{item.title}</strong>
              <small>
                {item.theme} · {item.difficulty}
              </small>
            </span>
            <span>{item.city_name}</span>
            <span>
              {item.duration_minutes} 分钟 / {item.distance_km} km
            </span>
            <span>{item.stop_count}</span>
            <span>
              <StatusTag status={item.content_status} />
            </span>
            <span className="row-actions">
              {actions[item.content_status] && (
                <button onClick={() => onTransition(item)}>
                  {actions[item.content_status]}
                </button>
              )}
              <button onClick={() => onEdit(item)}>编辑</button>
              <button className="danger-link" onClick={() => onDelete(item)}>
                删除
              </button>
            </span>
          </div>
        ))}
        {!rows.length && <TableEmpty text="还没有路线" />}
      </div>
    </ResourcePanel>
  );
}
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function StopsView({
  rows,
  onEdit,
  onDelete,
}: {
  rows: Stop[];
  onEdit: (x: Stop) => void;
  onDelete: (x: Stop) => void;
}) {
  return (
    <ResourcePanel eyebrow="STORY CATALOG" title={`${rows.length} 个故事站点`}>
      <div className="data-list">
        {rows.map((item) => (
          <article className="story-row" key={item.id}>
            <span className="position">
              {String(item.position).padStart(2, "0")}
            </span>
            <div className="data-main">
              <small>{item.route_title}</small>
              <h3>{item.story_title}</h3>
              <p>
                {item.title} · {item.address}
              </p>
            </div>
            <span
              className={item.has_challenge ? "completion yes" : "completion"}
            >
              {item.has_challenge ? "已配置问题" : "缺少问题"}
            </span>
            <RowActions
              onEdit={() => onEdit(item)}
              onDelete={() => onDelete(item)}
            />
          </article>
        ))}
        {!rows.length && <TableEmpty text="还没有故事站点" />}
      </div>
    </ResourcePanel>
  );
}
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function ChallengesView({
  rows,
  onEdit,
  onDelete,
}: {
  rows: Challenge[];
  onEdit: (x: Challenge) => void;
  onDelete: (x: Challenge) => void;
}) {
  return (
    <ResourcePanel eyebrow="QUESTION BANK" title={`${rows.length} 道互动问题`}>
      <div className="question-grid">
        {rows.map((item) => (
          <article className="question-card" key={item.id}>
            <div className="question-meta">
              <span>{item.route_title}</span>
              <small>{item.stop_title}</small>
            </div>
            <h3>{item.prompt}</h3>
            <ol>
              {item.options.map((option, index) => (
                <li
                  className={index === item.correct_option ? "correct" : ""}
                  key={`${index}-${option}`}
                >
                  {option}
                </li>
              ))}
            </ol>
            <div className="question-foot">
              <small>
                正确答案：{String.fromCharCode(65 + item.correct_option)}
              </small>
              <RowActions
                onEdit={() => onEdit(item)}
                onDelete={() => onDelete(item)}
              />
            </div>
          </article>
        ))}
        {!rows.length && <TableEmpty text="还没有互动问题" />}
      </div>
    </ResourcePanel>
  );
}

function MediaView({
  rows,
  request,
  onChanged,
  onDelete,
  setNotice,
}: {
  rows: Media[];
  request: <T>(p: string, i?: RequestInit) => Promise<T>;
  onChanged: () => void;
  onDelete: (x: Media) => void;
  setNotice: (x: string) => void;
}) {
  const [uploading, setUploading] = useState(false);
  const [hierarchy, setHierarchy] = useState<MediaHierarchy | null>(null);
  const loadHierarchy = useCallback(async () => {
    try { setHierarchy(await request<MediaHierarchy>("/media/hierarchy")); }
    catch (error) { setNotice(error instanceof Error ? error.message : "媒体层级读取失败"); }
  }, [request, setNotice]);
  useEffect(() => { const timer = window.setTimeout(() => void loadHierarchy(), 0); return () => window.clearTimeout(timer); }, [loadHierarchy]);
  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setUploading(true);
    try {
      const body = new FormData(event.currentTarget);
      await request("/media", { method: "POST", body });
      event.currentTarget.reset();
      onChanged();
      await loadHierarchy();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "上传失败");
    } finally {
      setUploading(false);
    }
  }
  function copy(path: string) {
    void navigator.clipboard.writeText(path);
    setNotice("资源路径已复制");
  }
  return (
    <>
      <section className="upload-panel">
        <div>
          <p className="eyebrow">UPLOAD ASSET</p>
          <h2>上传图片或音频</h2>
          <p>生产与测试共用同一套 OSS 对象；公共资源经 CDN 交付，私有资源只走鉴权访问。</p>
        </div>
        <form onSubmit={upload}>
          <label className="file-drop">
            <input name="file" type="file" accept="image/*,audio/*" required />
            <span>选择文件</span>
          </label>
          <input name="key" placeholder="资源标识（可选）" />
          <button className="primary-button" disabled={uploading}>
            {uploading ? "上传中…" : "上传资源"}
          </button>
        </form>
      </section>
      <ResourcePanel
        eyebrow="OSS ASSET HIERARCHY"
        title="城市 → 景点 → 资源"
      >
        {!hierarchy ? <p>正在读取 OSS 资源关系…</p> : <>
          <div className={hierarchy.readiness.ready ? "readiness-ok" : "readiness-blocked"}>
            <strong>{hierarchy.readiness.ready ? "OSS 共用资源已就绪" : "OSS 就绪检查未通过"}</strong>
            <span>公共 {hierarchy.readiness.public_count} · 私有 {hierarchy.readiness.private_count} · {hierarchy.readiness.cdn_base}</span>
            {!!hierarchy.readiness.blockers.length && <span>{hierarchy.readiness.blockers.join("；")}。请先迁移并重新检查，浏览器不会执行迁移命令。</span>}
          </div>
          <div className="media-tree">
            {hierarchy.cities.map((city) => <details key={city.id}><summary>{city.name}<span>{city.scenics.reduce((count, scenic) => count + scenic.assets.length, 0)} 项引用</span></summary>
              {city.scenics.map((scenic) => <details key={scenic.id}><summary>{scenic.title}<span>{scenic.assets.length} 项 · {storyStatusLabel(scenic.status)}</span></summary><div className="media-tree-assets">{scenic.assets.map((path) => <MediaHierarchyRow key={path} path={path} asset={hierarchy.assets[path]} rows={rows} copy={copy} onDelete={onDelete} />)}{!scenic.assets.length && <p className="muted">该景点暂无已登记资源</p>}</div></details>)}
            </details>)}
            <details><summary>未归属资源<span>{hierarchy.unassigned.length} 项</span></summary><div className="media-tree-assets">{hierarchy.unassigned.map((path) => <MediaHierarchyRow key={path} path={path} asset={hierarchy.assets[path]} rows={rows} copy={copy} onDelete={onDelete} />)}</div></details>
          </div>
        </>}
      </ResourcePanel>
    </>
  );
}

function MediaHierarchyRow({ path, asset, rows, copy, onDelete }: { path: string; asset: MediaHierarchy["assets"][string]; rows: Media[]; copy: (path: string) => void; onDelete: (item: Media) => void }) {
  const row = rows.find((item) => item.key === asset?.key);
  if (!asset) return null;
  return <article className="media-tree-row"><div><strong>{asset.key}</strong><small>{asset.scope === "public" ? "公共 OSS · CDN" : "私有 OSS · 鉴权访问"} · {asset.mime_type}</small><code>{asset.object_key}</code><small>{asset.reference_count} 处引用 · {(asset.usages || []).map((usage) => usage.role).join("、")}</small></div><div className="media-actions"><button onClick={() => copy(path)}>复制对象引用</button>{row && <button className="danger-link" onClick={() => onDelete(row)}>删除</button>}</div></article>;
}

// Kept temporarily for rollback compatibility; no active navigation points here.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function HomeStoriesWorkspace({
  request,
  setNotice,
}: {
  request: <T>(p: string, i?: RequestInit) => Promise<T>;
  setNotice: (x: string) => void;
}) {
  const [stories, setStories] = useState<HomeStoryView[]>([]);
  const [profiles, setProfiles] = useState<NarrationProfileView[]>([]);
  const [selectedArcId, setSelectedArcId] = useState("");
  const [profileId, setProfileId] = useState("");
  const [uploadDuration, setUploadDuration] = useState("");
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState({
    title: "",
    introduction: "",
    cover_image: "",
    selection_weight: 1,
    selected_track_id: "",
  });
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const selected = stories.find((item) => item.arc_id === selectedArcId);

  const load = useCallback(async () => {
    try {
      const [storyRows, profileRows] = await Promise.all([
        request<HomeStoryView[]>("/home-stories"),
        request<NarrationProfileView[]>("/narration/profiles"),
      ]);
      setStories(storyRows);
      setProfiles(profileRows.filter((item) => item.status !== "archived"));
      setSelectedArcId((current) =>
        storyRows.some((item) => item.arc_id === current)
          ? current
          : storyRows[0]?.arc_id || "",
      );
      setProfileId((current) =>
        profileRows.some((item) => item.id === current)
          ? current
          : profileRows.find((item) => item.is_default)?.id ||
            profileRows[0]?.id ||
            "",
      );
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "完整故事读取失败");
    }
  }, [request, setNotice]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      const publication = selected?.publication;
      setDraft({
        title: publication?.title || selected?.arc_title || "",
        introduction: publication?.introduction || "",
        cover_image: publication?.cover_image || "",
        selection_weight: publication?.selection_weight || 1,
        selected_track_id: publication?.selected_track_id || "",
      });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [selected]);
  useEffect(
    () => () => {
      audioRef.current?.pause();
    },
    [],
  );

  async function mutate(path: string, init: RequestInit, success: string) {
    setBusy(true);
    try {
      const value = await request<HomeStoryView>(path, init);
      setStories((current) =>
        current.map((item) => (item.arc_id === value.arc_id ? value : item)),
      );
      setNotice(success);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!selected) return;
    await mutate(
      `/home-stories/${selected.arc_id}`,
      { method: "PUT", body: JSON.stringify(draft) },
      "首页故事卡片已保存",
    );
  }

  async function generate() {
    if (!selected || !profileId) return;
    await mutate(
      `/home-stories/${selected.arc_id}/generate`,
      { method: "POST", body: JSON.stringify({ profile_id: profileId }) },
      "完整故事音频已生成，请试听后审核",
    );
  }

  async function upload(file: File | undefined) {
    if (!selected || !profileId || !file) return;
    const seconds = Number(uploadDuration);
    if (!Number.isFinite(seconds) || seconds <= 0) {
      setNotice("上传前请填写音频总时长（秒）");
      return;
    }
    const body = new FormData();
    body.set("profile_id", profileId);
    body.set("duration_ms", String(Math.round(seconds * 1000)));
    body.set("file", file);
    await mutate(
      `/home-stories/${selected.arc_id}/upload`,
      { method: "POST", body },
      "完整故事音频已上传，请试听后审核",
    );
  }

  async function transition(action: string, message: string) {
    if (!selected) return;
    if (
      ["publish", "withdraw", "archive"].includes(action) &&
      !window.confirm(`${message}？`)
    )
      return;
    await mutate(
      `/home-stories/${selected.arc_id}/${action}`,
      { method: "POST" },
      message,
    );
  }

  async function playTrack(track: HomeStoryTrackView) {
    try {
      audioRef.current?.pause();
      const payload = await request<ArrayBuffer>(track.playback_path);
      const url = URL.createObjectURL(new Blob([payload], { type: "audio/mpeg" }));
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.addEventListener("ended", () => URL.revokeObjectURL(url), {
        once: true,
      });
      await audio.play();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "音频试听失败");
    }
  }

  const status = selected?.publication?.status || "draft";
  const primaryAction =
    status === "draft" || status === "withdrawn"
      ? ["submit-review", "提交审核"]
      : status === "in_review"
        ? ["approve", "审核通过"]
        : status === "approved"
          ? ["publish", "发布到首页"]
          : status === "published"
            ? ["withdraw", "从首页撤回"]
            : null;

  return (
    <section className="home-story-workspace">
      <div className="home-story-list panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">STORY POOL</p>
            <h2>可听故事池</h2>
          </div>
          <span className="status-chip published">{stories.length} 篇</span>
        </div>
        <div className="home-story-list-items">
          {stories.map((item) => (
            <button
              key={item.arc_id}
              className={item.arc_id === selectedArcId ? "active" : ""}
              onClick={() => setSelectedArcId(item.arc_id)}
            >
              <i>{item.city_name.slice(0, 1)}</i>
              <span>
                <strong>{item.publication?.title || item.arc_title}</strong>
                <small>{item.city_name} · {item.route_title}</small>
              </span>
              <em>{storyStatusLabel(item.publication?.status || "draft")}</em>
            </button>
          ))}
          {!stories.length && <TableEmpty text="还没有可配置的完整故事" />}
        </div>
      </div>

      {selected && (
        <article className="home-story-editor panel">
          <div className="home-story-hero">
            <div>
              <p className="eyebrow">{selected.city_name} · {selected.route_title}</p>
              <h2>{draft.title || selected.arc_title}</h2>
              <p>从路线的完整故事正文生成音频；首页只会随机抽取已经审核发布、且文字哈希一致的内容。</p>
            </div>
            <span className={`status-chip ${status}`}>{storyStatusLabel(status)}</span>
          </div>

          <div className="home-story-form">
            <label className="field">
              首页标题
              <input
                value={draft.title}
                maxLength={255}
                onChange={(event) => setDraft({ ...draft, title: event.target.value })}
              />
            </label>
            <label className="field">
              一句话引子（可选）
              <textarea
                rows={3}
                value={draft.introduction}
                onChange={(event) =>
                  setDraft({ ...draft, introduction: event.target.value })
                }
                placeholder="留空时自动使用路线副标题"
              />
            </label>
            <div className="form-grid">
              <label className="field">
                封面资源路径（可选）
                <input
                  value={draft.cover_image}
                  onChange={(event) =>
                    setDraft({ ...draft, cover_image: event.target.value })
                  }
                  placeholder="留空时自动使用路线封面"
                />
              </label>
              <label className="field">
                随机权重（0–100）
                <input
                  type="number"
                  min="0"
                  max="100"
                  value={draft.selection_weight}
                  onChange={(event) =>
                    setDraft({
                      ...draft,
                      selection_weight: Number(event.target.value),
                    })
                  }
                />
              </label>
            </div>
            <button className="ghost-button" disabled={busy || status === "published"} onClick={() => void save()}>
              保存卡片内容
            </button>
          </div>

          <section className="home-story-transcript">
            <div>
              <p className="eyebrow">CANONICAL TRANSCRIPT</p>
              <h3>完整故事正文</h3>
              <code>{selected.script_version} · {selected.transcript_hash.slice(0, 12)}</code>
            </div>
            <p>{selected.transcript}</p>
          </section>

          <section className="home-story-audio">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">VOICE REVIEW</p>
                <h3>生成与试听</h3>
              </div>
              <div className="home-story-generate">
                <select value={profileId} onChange={(event) => setProfileId(event.target.value)}>
                  {profiles.map((profile) => (
                    <option key={profile.id} value={profile.id}>{profile.display_name}</option>
                  ))}
                </select>
                <button className="primary-button" disabled={busy || !profileId || status === "published"} onClick={() => void generate()}>
                  生成当前正文
                </button>
                <input
                  aria-label="上传音频时长（秒）"
                  type="number"
                  min="1"
                  step="0.1"
                  placeholder="时长（秒）"
                  value={uploadDuration}
                  onChange={(event) => setUploadDuration(event.target.value)}
                />
                <label className={`ghost-button ${busy || !profileId || status === "published" ? "disabled" : ""}`}>
                  上传成品音频
                  <input
                    hidden
                    type="file"
                    accept="audio/mpeg,audio/mp4,audio/x-m4a,audio/wav,audio/x-wav"
                    disabled={busy || !profileId || status === "published"}
                    onChange={(event) => {
                      void upload(event.target.files?.[0]);
                      event.target.value = "";
                    }}
                  />
                </label>
              </div>
            </div>
            <div className="home-story-track-grid">
              {selected.tracks.map((track) => (
                <article key={track.id} className={track.is_current ? "current" : "stale"}>
                  <span>{track.is_current ? "正文一致" : "已过期"}</span>
                  <strong>{track.profile_name}</strong>
                  <small>{storyStatusLabel(track.status)} · {formatStoryDuration(track.duration_ms)}</small>
                  <button className="ghost-button" onClick={() => void playTrack(track)}>试听</button>
                  <label>
                    <input
                      type="radio"
                      name="home-story-track"
                      checked={draft.selected_track_id === track.id}
                      disabled={!track.is_current || status === "published"}
                      onChange={() => setDraft({ ...draft, selected_track_id: track.id })}
                    />
                    设为发布音频
                  </label>
                </article>
              ))}
              {!selected.tracks.length && <p className="home-story-empty">还没有音频。选择音色后生成一个试听版本。</p>}
            </div>
          </section>

          <section className={selected.blockers.length ? "story-blockers" : "story-blockers ready"}>
            <strong>{selected.blockers.length ? "发布前还差这些" : "发布校验已通过"}</strong>
            {selected.blockers.length > 0 && (
              <ul>{selected.blockers.map((item) => <li key={item}>{item}</li>)}</ul>
            )}
          </section>
          <div className="publish-bar">
            <span>只有正文、音频、路线和卡片信息同时有效，客户端才会抽到这个故事。</span>
            {status !== "published" && status !== "archived" && (
              <button className="danger-link" disabled={busy} onClick={() => void transition("archive", "故事已归档")}>归档</button>
            )}
            {primaryAction && (
              <button
                className="primary-button"
                disabled={busy || (primaryAction[0] === "publish" && !selected.ready_to_publish)}
                onClick={() => void transition(primaryAction[0], primaryAction[1])}
              >
                {primaryAction[1]}
              </button>
            )}
          </div>
        </article>
      )}
    </section>
  );
}

function ScenicContentWorkspace({
  routes,
  stops,
  request,
  setNotice,
  onChanged,
  onEditScenic,
  onDeleteStop,
}: {
  routes: Route[];
  stops: Stop[];
  request: <T>(p: string, i?: RequestInit) => Promise<T>;
  setNotice: (x: string) => void;
  onChanged: () => void;
  onEditScenic: (x: Route) => void;
  onDeleteStop: (x: Stop) => void;
}) {
  const [query, setQuery] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [routeId, setRouteId] = useState("");
  useEffect(() => {
    const timer = window.setTimeout(() => {
      const params = new URLSearchParams(window.location.search);
      const recent = params.get("scenic") || localStorage.getItem("jiandi-recent-scenic") || "";
      setRouteId(routes.some((route) => route.id === recent) ? recent : routes[0]?.id || "");
    }, 0);
    return () => window.clearTimeout(timer);
  }, [routes]);
  const selected = routes.find((route) => route.id === routeId);
  const filtered = routes.filter((route) =>
    `${route.city_name || ""} ${route.title} ${route.slug}`.toLowerCase().includes(query.trim().toLowerCase()),
  );
  const grouped = filtered.reduce<Record<string, Route[]>>((result, route) => {
    (result[route.city_name || "未命名城市"] ||= []).push(route);
    return result;
  }, {});
  function choose(next: Route) {
    setRouteId(next.id);
    localStorage.setItem("jiandi-recent-scenic", next.id);
    const url = new URL(window.location.href);
    url.searchParams.set("scenic", next.id);
    window.history.replaceState(null, "", url);
    setPickerOpen(false);
  }
  return (
    <section className="scenic-shell">
      <article className="panel scenic-context">
        <div>
          <p className="eyebrow">SELECTED SCENIC</p>
          <h2>{selected ? `${selected.city_name} · ${selected.title}` : "请选择景点"}</h2>
          <p>{selected ? `${selected.stop_count} 个站点 · ${storyStatusLabel(selected.content_status)}` : "选择后集中维护站点、碎片、标签和出发前内容。"}</p>
        </div>
        <div className="scenic-context-actions">
          {selected && <button className="ghost-button" onClick={() => onEditScenic(selected)}>编辑景点信息</button>}
          <button className="primary-button" onClick={() => setPickerOpen(true)}>选择景点</button>
        </div>
      </article>
      {pickerOpen && (
        <div className="modal-backdrop">
          <section className="modal scenic-picker" role="dialog" aria-modal="true" aria-label="选择景点">
            <div className="modal-head"><div><p className="eyebrow">SCENIC PICKER</p><h2>选择景点</h2></div><button aria-label="关闭景点选择" onClick={() => setPickerOpen(false)}>×</button></div>
            <input aria-label="搜索景点" placeholder="搜索城市、景点名称或 slug" value={query} onChange={(event) => setQuery(event.target.value)} />
            <div className="scenic-groups">
              {Object.entries(grouped).map(([city, rows]) => <section key={city}><h3>{city}</h3><div className="scenic-options">{rows.map((route) => <button key={route.id} className={route.id === routeId ? "scenic-option selected" : "scenic-option"} onClick={() => choose(route)}><span className="scenic-cover">{route.hero_image ? <img src={route.hero_image} alt="" /> : route.title.slice(0, 1)}</span><span><strong>{route.title}</strong><small>{route.stop_count} 个站点 · {storyStatusLabel(route.content_status)}</small></span></button>)}</div></section>)}
              {!filtered.length && <TableEmpty text="没有匹配的景点" />}
            </div>
          </section>
        </div>
      )}
      {selected && <>
        <PredepartureEditor key={`pretrip-${routeId}`} route={selected} request={request} setNotice={setNotice} />
        <ScenicNodesWorkspace
          key={`nodes-${routeId}`}
          route={selected}
          stops={stops.filter((stop) => stop.route_id === routeId)}
          request={request}
          setNotice={setNotice}
          onChanged={onChanged}
          onDeleteStop={onDeleteStop}
        />
      </>}
    </section>
  );
}

function PredepartureEditor({ route, request, setNotice }: { route: Route; request: <T>(p: string, i?: RequestInit) => Promise<T>; setNotice: (x: string) => void }) {
  const [pretrip, setPretrip] = useState<Data | null>(null);
  const [profiles, setProfiles] = useState<NarrationProfileView[]>([]);
  const load = useCallback(async () => {
    try {
      const [content, voiceProfiles] = await Promise.all([request<Data>(`/routes/${route.id}/pretrip`), request<NarrationProfileView[]>("/narration/profiles")]);
      setPretrip(content); setProfiles(voiceProfiles);
    } catch (error) { setNotice(error instanceof Error ? error.message : "出发前内容读取失败"); }
  }, [request, route.id, setNotice]);
  useEffect(() => { const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer); }, [load]);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      setPretrip(await request<Data>(`/routes/${route.id}/pretrip`, { method: "PUT", body: JSON.stringify({ expected_version: num(pretrip?.version, 0), introduction_text: String(form.get("introduction_text") || ""), introduction_script_version: str(pretrip?.introduction_script_version) || "1", selected_intro_track_id: String(form.get("selected_intro_track_id") || "") || null }) }));
      setNotice("出发前内容已保存");
    } catch (error) { setNotice(error instanceof Error ? error.message : "出发前内容保存失败"); }
  }
  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try { await request(`/routes/${route.id}/pretrip/audio`, { method: "POST", body: new FormData(event.currentTarget) }); await load(); setNotice("出发前音频已上传 OSS 并通过审核"); }
    catch (error) { setNotice(error instanceof Error ? error.message : "音频上传失败"); }
  }
  async function transition(action: string) { try { await request(`/routes/${route.id}/pretrip/${action}`, { method: "POST" }); await load(); setNotice(action === "publish" ? "出发前内容已发布" : "出发前内容已撤回"); } catch (error) { setNotice(error instanceof Error ? error.message : "状态更新失败"); } }
  return <ResourcePanel eyebrow="PRE-DEPARTURE" title="出发前介绍与语音">
    {!pretrip ? <p>正在读取…</p> : <>
      <form className="form-grid" onSubmit={save}>
        <Field label="简短介绍"><textarea name="introduction_text" rows={6} maxLength={1200} defaultValue={str(pretrip.introduction_text)} required /></Field>
        <Field label="匹配的已审核语音"><select name="selected_intro_track_id" defaultValue={str(pretrip.selected_intro_track_id)}><option value="">尚未选择</option>{(pretrip.tracks as Data[] || []).filter((track) => track.matches_current_text && track.status === "published").map((track) => <option key={str(track.id)} value={str(track.id)}>{str(track.profile_id)} · {Math.round(num(track.duration_ms) / 1000)} 秒</option>)}</select></Field>
        <div className="import-actions"><button className="primary-button">保存</button>{pretrip.status === "published" ? <button type="button" onClick={() => void transition("withdraw")}>撤回</button> : <button type="button" onClick={() => void transition("publish")}>发布</button>}</div>
      </form>
      <form className="inline-upload" onSubmit={upload}><input name="file" type="file" accept="audio/*" required /><select name="profile_id" required><option value="">选择音色</option>{profiles.filter((profile) => profile.status === "published").map((profile) => <option key={profile.id} value={profile.id}>{profile.display_name}</option>)}</select><button>上传至公共 OSS</button></form>
      <p className="muted">客户端只显示紧凑播放图标；修改文字会立即使旧音频失效。</p>
    </>}
  </ResourcePanel>;
}

function ScenicNodesWorkspace({
  route,
  stops,
  request,
  setNotice,
  onChanged,
  onDeleteStop,
}: {
  route: Route;
  stops: Stop[];
  request: <T>(p: string, i?: RequestInit) => Promise<T>;
  setNotice: (x: string) => void;
  onChanged: () => void;
  onDeleteStop: (x: Stop) => void;
}) {
  const [graph, setGraph] = useState<RouteGraph | null>(null);
  const [busy, setBusy] = useState(false);
  const [validation, setValidation] = useState<GraphValidation | null>(null);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      setGraph(await request<RouteGraph>(`/routes/${route.id}/content`));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "景点节点读取失败");
    } finally {
      setBusy(false);
    }
  }, [request, route.id, setNotice]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function persistGraph(next: RouteGraph, success = "节点内容已保存") {
    setBusy(true);
    try {
      const value = await request<{ content: RouteGraph; validation: GraphValidation }>(
        `/routes/${route.id}/content`,
        { method: "PUT", body: JSON.stringify(next) },
      );
      setGraph(value.content);
      setValidation(value.validation);
      setNotice(success);
      onChanged();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "节点保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function saveManagedNode(index: number, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!graph) return;
    const form = new FormData(event.currentTarget);
    const current = graph.fragments[index];
    const currentStop = (current.stop as Data | null) || {};
    const currentRegion = (current.trigger_region as Data | null) || {};
    const title = String(form.get("title") || "").trim();
    const story = String(form.get("story_content") || "").trim();
    const tags = parseTagText(String(form.get("experience_tags") || ""));
    const latitude = Number(form.get("latitude"));
    const longitude = Number(form.get("longitude"));
    const radius = Number(form.get("arrival_radius_m"));
    const nextFragment: Data = {
      ...current,
      title,
      narration_script: story,
      transcript: story,
      experience_tags: tags,
      stop: {
        ...currentStop,
        title,
        story_title: title,
        story_body: story,
        address: String(form.get("address") || "").trim(),
        latitude,
        longitude,
        arrival_radius_m: radius,
        experience_tags: tags,
      },
      trigger_region: {
        ...currentRegion,
        latitude,
        longitude,
        entry_radius_m: radius,
        exit_radius_m: Math.max(radius + 20, num(currentRegion.exit_radius_m, radius + 20)),
      },
    };
    const next = {
      ...graph,
      fragments: graph.fragments.map((item, itemIndex) =>
        itemIndex === index ? nextFragment : item,
      ),
    };
    await persistGraph(next);
  }

  async function saveLegacyStop(stop: Stop, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const title = String(form.get("title") || "").trim();
    const story = String(form.get("story_body") || "").trim();
    try {
      await request(`/stops/${stop.id}`, {
        method: "PUT",
        body: JSON.stringify({
          ...stop,
          title,
          kicker: stop.kicker || title,
          story_title: title,
          story_body: story,
          insight: stop.insight || story,
          address: String(form.get("address") || "").trim(),
          latitude: Number(form.get("latitude")),
          longitude: Number(form.get("longitude")),
          arrival_radius_m: Number(form.get("arrival_radius_m")),
          experience_tags: parseTagText(String(form.get("experience_tags") || "")),
        }),
      });
      setNotice("节点内容已保存");
      onChanged();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "节点保存失败");
    }
  }

  async function validate() {
    try {
      const value = await request<GraphValidation>(`/routes/${route.id}/validate`, { method: "POST" });
      setValidation(value);
      setNotice(value.valid ? "景点内容校验通过" : `还有 ${value.errors.length} 个发布问题`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "校验失败");
    }
  }

  async function advanceLifecycle() {
    const status = str(graph?.route.content_status || route.content_status);
    const action: Record<string, [string, string]> = {
      draft: ["submit-review", "景点已提交审核"],
      in_review: ["verify", "景点已通过审核"],
      verified: ["publish", "景点已发布到客户端"],
      published: ["archive", "景点已归档"],
    };
    if (!action[status]) return;
    try {
      await request(`/routes/${route.id}/${action[status][0]}`, { method: "POST" });
      await load();
      onChanged();
      setNotice(action[status][1]);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "状态更新失败");
    }
  }

  const managedStopIds = new Set(
    (graph?.fragments || []).map((fragment) => str((fragment.stop as Data | null)?.id)).filter(Boolean),
  );
  const legacyStops = stops.filter((stop) => !managedStopIds.has(stop.id));

  return (
    <section className="scenic-node-workspace">
      {graph?.story_arc && (
        <CompactNarrationPanel routeId={route.id} request={request} setNotice={setNotice} />
      )}
      <article className="panel node-section-heading">
        <div>
          <p className="eyebrow">CONTENT NODES</p>
          <h2>景点文案与位置</h2>
          <p>一个节点一张卡片，只配置标题、文案、地址、定位和标签。</p>
        </div>
        <span>{(graph?.fragments.length || 0) + legacyStops.length} 个节点</span>
      </article>
      <div className="scenic-node-list">
        {graph?.fragments.map((fragment, index) => {
          const stop = (fragment.stop as Data | null) || {};
          const region = (fragment.trigger_region as Data | null) || {};
          return (
            <form className="panel scenic-node-card" key={str(fragment.id)} onSubmit={(event) => void saveManagedNode(index, event)}>
              <div className="scenic-node-title"><span>{String(index + 1).padStart(2, "0")}</span><strong>{str(fragment.title) || "未命名节点"}</strong></div>
              <Field label="节点名称"><input name="title" defaultValue={str(fragment.title)} required /></Field>
              <Field label="故事文案"><textarea name="story_content" rows={7} defaultValue={str(fragment.narration_script || fragment.transcript)} required /></Field>
              <Field label="地址"><input name="address" defaultValue={str(stop.address)} required /></Field>
              <div className="form-grid three">
                <Field label="纬度"><input name="latitude" type="number" step="any" defaultValue={num(stop.latitude, num(region.latitude))} required /></Field>
                <Field label="经度"><input name="longitude" type="number" step="any" defaultValue={num(stop.longitude, num(region.longitude))} required /></Field>
                <Field label="到达半径（米）"><input name="arrival_radius_m" type="number" min="1" defaultValue={num(stop.arrival_radius_m, num(region.entry_radius_m, 60))} required /></Field>
              </div>
              <TagEditor name="experience_tags" tags={stringList(fragment.experience_tags)} />
              <div className="scenic-node-actions"><button className="primary-button" disabled={busy}>保存这个节点</button></div>
            </form>
          );
        })}
        {legacyStops.map((stop) => (
          <form className="panel scenic-node-card" key={stop.id} onSubmit={(event) => void saveLegacyStop(stop, event)}>
            <div className="scenic-node-title"><span>{String(stop.position).padStart(2, "0")}</span><strong>{stop.title}</strong><small>兼容节点</small></div>
            <Field label="节点名称"><input name="title" defaultValue={stop.title} required /></Field>
            <Field label="故事文案"><textarea name="story_body" rows={7} defaultValue={stop.story_body} required /></Field>
            <Field label="地址"><input name="address" defaultValue={stop.address} required /></Field>
            <div className="form-grid three">
              <Field label="纬度"><input name="latitude" type="number" step="any" defaultValue={stop.latitude} required /></Field>
              <Field label="经度"><input name="longitude" type="number" step="any" defaultValue={stop.longitude} required /></Field>
              <Field label="到达半径（米）"><input name="arrival_radius_m" type="number" min="1" defaultValue={stop.arrival_radius_m} required /></Field>
            </div>
            <TagEditor name="experience_tags" tags={stop.experience_tags} />
            <div className="scenic-node-actions">
              <button type="button" className="danger-link" onClick={() => onDeleteStop(stop)}>删除</button>
              <button className="primary-button">保存这个节点</button>
            </div>
          </form>
        ))}
        {!busy && !graph?.fragments.length && !legacyStops.length && <TableEmpty text="这个景点还没有内容节点，点击右上角添加节点" />}
      </div>
      {validation && !validation.valid && <IssueList title="发布前需要处理" rows={validation.errors} empty="没有阻断问题" />}
      <div className="publish-bar">
        <span>技术字段由系统保留；这里只维护实际会用到的内容。</span>
        <button className="ghost-button" onClick={() => void validate()}>校验</button>
        <button className="primary-button" onClick={() => void advanceLifecycle()}>{lifecycleAction(str(graph?.route.content_status || route.content_status))}</button>
      </div>
    </section>
  );
}

function CompactNarrationPanel({ routeId, request, setNotice }: { routeId: string; request: <T>(p: string, i?: RequestInit) => Promise<T>; setNotice: (x: string) => void }) {
  const [profiles, setProfiles] = useState<NarrationProfileView[]>([]);
  const [profileId, setProfileId] = useState("");
  const [coverage, setCoverage] = useState<NarrationCoverage | null>(null);
  const [configured, setConfigured] = useState(false);
  const [busy, setBusy] = useState(false);

  const loadProfiles = useCallback(async () => {
    try {
      const [rows, config] = await Promise.all([
        request<NarrationProfileView[]>("/narration/profiles"),
        request<NarrationConfigView>("/narration/config"),
      ]);
      setProfiles(rows);
      setConfigured(config.credentials_configured);
      setProfileId((current) => rows.some((row) => row.id === current) ? current : rows.find((row) => row.is_default)?.id || rows[0]?.id || "");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "景点语音读取失败");
    }
  }, [request, setNotice]);

  const loadCoverage = useCallback(async () => {
    if (!profileId) return setCoverage(null);
    try {
      setCoverage(await request<NarrationCoverage>(`/routes/${routeId}/narration/coverage?profile_id=${encodeURIComponent(profileId)}`));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "语音覆盖读取失败");
    }
  }, [profileId, request, routeId, setNotice]);

  useEffect(() => { const timer = window.setTimeout(() => void loadProfiles(), 0); return () => window.clearTimeout(timer); }, [loadProfiles]);
  useEffect(() => { const timer = window.setTimeout(() => void loadCoverage(), 0); return () => window.clearTimeout(timer); }, [loadCoverage]);

  async function generate(regenerateAll: boolean) {
    if (!profileId) return;
    setBusy(true);
    try {
      const result = await request<NarrationBatchResult>(`/routes/${routeId}/narration/generate`, {
        method: "POST",
        body: JSON.stringify({ profile_id: profileId, regenerate_all: regenerateAll }),
      });
      setCoverage(result.coverage);
      setNotice(result.failed_count ? `已生成 ${result.generated_count} 条，${result.failed_count} 条失败` : `已生成并保存 ${result.generated_count} 条景点语音`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "景点语音生成失败");
    } finally {
      setBusy(false);
    }
  }

  async function publish() {
    if (!profileId) return;
    setBusy(true);
    try {
      await request(`/narration/profiles/${profileId}/publish`, { method: "POST", body: JSON.stringify({ route_id: routeId }) });
      await loadProfiles();
      setNotice("景点语音已发布到客户端");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "语音发布失败");
    } finally {
      setBusy(false);
    }
  }

  const selected = profiles.find((profile) => profile.id === profileId);
  const incomplete = (coverage?.missing.length || 0) + (coverage?.stale.length || 0);
  return (
    <article className="panel compact-narration-panel">
      <div><p className="eyebrow">SCENIC NARRATION</p><h2>景点语音</h2><p>选一个现有音色，一次生成这个景点的全部节点。</p></div>
      <Field label="讲述音色"><select value={profileId} onChange={(event) => setProfileId(event.target.value)}><option value="">暂无音色</option>{profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.display_name}</option>)}</select></Field>
      <div className="compact-narration-status"><strong>{coverage?.complete_count || 0}/{coverage?.total || 0}</strong><span>节点语音已覆盖</span>{incomplete > 0 && <small>还缺或已过期 {incomplete} 条</small>}</div>
      <div className="compact-narration-actions">
        <button className="primary-button" disabled={busy || !configured || !profileId} onClick={() => void generate(incomplete === 0)}>{busy ? "处理中…" : incomplete ? `生成缺失的 ${incomplete} 条` : "重新生成全部语音"}</button>
        {incomplete > 0 && <button className="ghost-button" disabled={busy || !configured} onClick={() => void generate(true)}>重新生成全部</button>}
        {selected && selected.status !== "published" && <button className="ghost-button" disabled={busy || !coverage?.ready} onClick={() => void publish()}>发布到客户端</button>}
      </div>
      {!configured && <small className="voice-route-warning">服务器尚未配置语音服务</small>}
    </article>
  );
}

// Legacy rollback surface; the active scenic UI is ScenicNodesWorkspace.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function FragmentedRouteWorkspace({
  routes,
  selectedRouteId,
  media,
  request,
  setNotice,
  onChanged,
}: {
  routes: Route[];
  selectedRouteId?: string;
  media: Media[];
  request: <T>(p: string, i?: RequestInit) => Promise<T>;
  setNotice: (x: string) => void;
  onChanged: () => void;
}) {
  const managedRoutes = routes.filter(
    (route) => Boolean(route.published_at) || route.stop_count > 0,
  );
  const [routeId] = useState(selectedRouteId || managedRoutes[0]?.id || routes[0]?.id || "");
  const [graph, setGraph] = useState<RouteGraph | null>(null);
  const [validation, setValidation] = useState<GraphValidation | null>(null);
  const [jsonMode, setJsonMode] = useState(false);
  const [jsonContent, setJsonContent] = useState("");
  const [busy, setBusy] = useState(false);
  const [narrationProfiles, setNarrationProfiles] = useState<NarrationProfileView[]>([]);
  const [narrationProfileId, setNarrationProfileId] = useState("");
  const [narrationCoverage, setNarrationCoverage] = useState<NarrationCoverage | null>(null);

  const loadNarrationProfiles = useCallback(async () => {
    try {
      const rows = await request<NarrationProfileView[]>("/narration/profiles");
      setNarrationProfiles(rows);
      setNarrationProfileId((current) =>
        rows.some((item) => item.id === current)
          ? current
          : rows.find((item) => item.is_default)?.id || rows[0]?.id || "",
      );
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "读取音色档案失败");
    }
  }, [request, setNotice]);

  const load = useCallback(
    async (id: string) => {
      if (!id) {
        setGraph(null);
        return;
      }
      setBusy(true);
      try {
        const value = await request<RouteGraph>(`/routes/${id}/content`);
        setGraph(value);
        setJsonContent(JSON.stringify(value, null, 2));
        setValidation(null);
      } catch (error) {
        setNotice(error instanceof Error ? error.message : "读取碎片路线失败");
      } finally {
        setBusy(false);
      }
    },
    [request, setNotice],
  );

  useEffect(() => {
    if (!routeId) return;
    const timer = window.setTimeout(() => void load(routeId), 0);
    return () => window.clearTimeout(timer);
  }, [routeId, load]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadNarrationProfiles(), 0);
    return () => window.clearTimeout(timer);
  }, [loadNarrationProfiles]);

  const loadNarrationCoverage = useCallback(async () => {
    if (!routeId || !narrationProfileId) {
      setNarrationCoverage(null);
      return;
    }
    try {
      setNarrationCoverage(await request<NarrationCoverage>(
        `/routes/${routeId}/narration/coverage?profile_id=${encodeURIComponent(narrationProfileId)}`,
      ));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "读取音色覆盖率失败");
    }
  }, [narrationProfileId, request, routeId, setNotice]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadNarrationCoverage(), 0);
    return () => window.clearTimeout(timer);
  }, [loadNarrationCoverage]);

  const selectedNarrationProfile = narrationProfiles.find(
    (item) => item.id === narrationProfileId,
  );

  async function refreshNarration() {
    await loadNarrationProfiles();
    await loadNarrationCoverage();
  }

  function updateArc(key: string, value: unknown) {
    setGraph((current) =>
      current
        ? {
            ...current,
            story_arc: { ...(current.story_arc || {}), [key]: value },
          }
        : current,
    );
  }
  function updateFragment(index: number, key: string, value: unknown) {
    setGraph((current) => {
      if (!current) return current;
      const fragments = current.fragments.map((item, itemIndex) =>
        itemIndex === index ? { ...item, [key]: value } : item,
      );
      return { ...current, fragments };
    });
  }
  function updateCollection(
    collection: "sources" | "claims",
    index: number,
    key: string,
    value: unknown,
  ) {
    setGraph((current) => {
      if (!current) return current;
      const rows = current[collection].map((item, itemIndex) =>
        itemIndex === index ? { ...item, [key]: value } : item,
      );
      return { ...current, [collection]: rows };
    });
  }
  function updateCausal(index: number, value: string) {
    const rows = Array.isArray(graph?.story_arc?.causal_model)
      ? [...(graph!.story_arc!.causal_model as Data[])]
      : [];
    rows[index] = { ...rows[index], text: value };
    updateArc("causal_model", rows);
  }
  function moveCausal(index: number, direction: -1 | 1) {
    const rows = Array.isArray(graph?.story_arc?.causal_model)
      ? [...(graph!.story_arc!.causal_model as Data[])]
      : [];
    const target = index + direction;
    if (target < 0 || target >= rows.length) return;
    [rows[index], rows[target]] = [rows[target], rows[index]];
    updateArc("causal_model", rows);
  }
  function updateNestedFragment(
    index: number,
    section: "trigger_region" | "photo_mission",
    key: string,
    value: unknown,
  ) {
    setGraph((current) => {
      if (!current) return current;
      const fragments = current.fragments.map((item, itemIndex) =>
        itemIndex === index
          ? {
              ...item,
              [section]: {
                ...((item[section] as Data | null) || {}),
                [key]: value,
              },
            }
          : item,
      );
      return { ...current, fragments };
    });
  }
  function applyJson() {
    try {
      const value = JSON.parse(jsonContent) as RouteGraph;
      setGraph(value);
      setNotice("JSON 已应用到编辑器，尚未保存");
    } catch {
      setNotice("JSON 格式不正确");
    }
  }
  async function save() {
    if (!graph || !routeId) return;
    setBusy(true);
    try {
      const value = await request<{
        content: RouteGraph;
        validation: GraphValidation;
      }>(`/routes/${routeId}/content`, {
        method: "PUT",
        body: JSON.stringify(graph),
      });
      setGraph(value.content);
      setJsonContent(JSON.stringify(value.content, null, 2));
      setValidation(value.validation);
      setNotice("草稿已保存");
      onChanged();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }
  async function validate() {
    if (!routeId) return;
    setBusy(true);
    try {
      const value = await request<GraphValidation>(
        `/routes/${routeId}/validate`,
        { method: "POST" },
      );
      setValidation(value);
      setNotice(
        value.valid
          ? "校验通过，可以发布"
          : `发现 ${value.errors.length} 个阻断问题`,
      );
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "校验失败");
    } finally {
      setBusy(false);
    }
  }
  async function advanceLifecycle() {
    if (!routeId || !graph) return;
    const status = str(graph.route.content_status);
    const transition: Record<string, { endpoint: string; message: string }> = {
      draft: { endpoint: "submit-review", message: "路线已提交审核" },
      in_review: { endpoint: "verify", message: "路线已通过审核，尚未发布" },
      verified: { endpoint: "publish", message: "路线已发布到客户端" },
      published: { endpoint: "archive", message: "路线已归档下线" },
    };
    const action = transition[status];
    if (!action) return;
    if (
      (status === "verified" || status === "published") &&
      !window.confirm(
        status === "verified"
          ? "确认发布这条路线？已有用户行程后将锁定内容版本。"
          : "确认归档这条路线？既有用户仍可继续行程。",
      )
    )
      return;
    setBusy(true);
    try {
      const value = await request<{
        route: Data;
        validation?: GraphValidation;
      }>(`/routes/${routeId}/${action.endpoint}`, { method: "POST" });
      setGraph((current) =>
        current
          ? { ...current, route: { ...current.route, ...value.route } }
          : current,
      );
      if (value.validation) setValidation(value.validation);
      setNotice(action.message);
      onChanged();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "状态变更失败");
    } finally {
      setBusy(false);
    }
  }
  function download() {
    if (!graph) return;
    const blob = new Blob([JSON.stringify(graph, null, 2)], {
      type: "application/json",
    });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${str(graph.package_id) || routeId}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
  }

  return (
    <section className="fragmented-workspace">
      <article className="panel fragmented-toolbar">
        <div>
          <p className="eyebrow">ROUTE PACKAGE</p>
          <h2>配置、校验并发布完整故事图</h2>
          <p>
            路线、故事弧、旁白、定位触发、照片任务、史实主张和来源均由后台配置。
          </p>
        </div>
        <div className="fragmented-actions">
          <strong>{routes.find((route) => route.id === routeId)?.title}</strong>
          <button
            className="ghost-button"
            onClick={() => void load(routeId)}
            disabled={busy}
          >
            重新读取
          </button>
          <button className="ghost-button" onClick={download} disabled={!graph}>
            导出 JSON
          </button>
        </div>
      </article>
      {!graph?.story_arc ? (
        <article className="panel fragmented-empty">
          <span>弧</span>
          <h2>这条路线还没有碎片故事图</h2>
          <p>
            请先在“批量导入”中导入完整路线包。导入后可在这里持续修改并发布，无需改客户端或后端代码。
          </p>
        </article>
      ) : (
        <>
          <div className="fragmented-switch">
            <button
              className={!jsonMode ? "active" : ""}
              onClick={() => setJsonMode(false)}
            >
              结构化编辑
            </button>
            <button
              className={jsonMode ? "active" : ""}
              onClick={() => {
                setJsonMode(true);
                setJsonContent(JSON.stringify(graph, null, 2));
              }}
            >
              高级 JSON
            </button>
            <span>
              {str(graph.package_id)} · {str(graph.package_version)}
            </span>
          </div>
          <NarrationProfilePanel
            routeId={routeId}
            profiles={narrationProfiles}
            selectedProfileId={narrationProfileId}
            coverage={narrationCoverage}
            request={request}
            setNotice={setNotice}
            onSelect={setNarrationProfileId}
            onChanged={() => void refreshNarration()}
          />
          {jsonMode ? (
            <article className="panel graph-json">
              <textarea
                value={jsonContent}
                onChange={(event) => setJsonContent(event.target.value)}
                spellCheck={false}
              />
              <button className="ghost-button" onClick={applyJson}>
                应用 JSON
              </button>
            </article>
          ) : (
            <div className="fragmented-grid">
              <article className="panel arc-editor">
                <div className="panel-heading">
                  <div>
                    <p className="eyebrow">STORY ARC</p>
                    <h2>完整故事</h2>
                  </div>
                  <StatusTag status={str(graph.route.content_status)} />
                </div>
                <Field label="核心问题">
                  <textarea
                    rows={2}
                    value={str(graph.story_arc.central_question)}
                    onChange={(event) =>
                      updateArc("central_question", event.target.value)
                    }
                  />
                </Field>
                <Field label="完整故事">
                  <textarea
                    rows={8}
                    value={str(graph.story_arc.complete_story)}
                    onChange={(event) =>
                      updateArc("complete_story", event.target.value)
                    }
                  />
                </Field>
                <Field label="脚本版本">
                  <input
                    value={str(graph.story_arc.script_version)}
                    onChange={(event) =>
                      updateArc("script_version", event.target.value)
                    }
                  />
                </Field>
                <div className="causal-builder">
                  <div className="fragment-subhead">最终因果链</div>
                  {(
                    (graph.story_arc.causal_model as Data[] | undefined) ?? []
                  ).map((item, index, rows) => (
                    <div className="causal-row" key={str(item.id)}>
                      <span>{index + 1}</span>
                      <input
                        value={str(item.text)}
                        onChange={(event) =>
                          updateCausal(index, event.target.value)
                        }
                      />
                      <button
                        aria-label="上移"
                        disabled={index === 0}
                        onClick={() => moveCausal(index, -1)}
                      >
                        ↑
                      </button>
                      <button
                        aria-label="下移"
                        disabled={index === rows.length - 1}
                        onClick={() => moveCausal(index, 1)}
                      >
                        ↓
                      </button>
                    </div>
                  ))}
                </div>
                <div className="graph-counts">
                  <span>
                    <b>{graph.fragments.length}</b> 条线索
                  </span>
                  <span>
                    <b>{graph.claims.length}</b> 条史实主张
                  </span>
                  <span>
                    <b>{graph.sources.length}</b> 个来源
                  </span>
                  <span>
                    <b>{graph.required_photo_mission_count}</b> 个阻塞式照片任务（建议保持 0）
                  </span>
                </div>
              </article>
              <div className="fragment-list">
                {graph.fragments.map((fragment, index) => {
                  const region = (fragment.trigger_region as Data | null) || {};
                  const mission = (fragment.photo_mission as Data | null) || {};
                  return (
                    <article
                      className="panel fragment-card"
                      key={str(fragment.id) || index}
                    >
                      <div className="fragment-heading">
                        <span>{String(index + 1).padStart(2, "0")}</span>
                        <div>
                          <small>{str(fragment.id)}</small>
                          <h2>{str(fragment.title) || "未命名线索"}</h2>
                        </div>
                      </div>
                      <div className="form-grid">
                        <Field label="线索标题">
                          <input
                            value={str(fragment.title)}
                            onChange={(event) =>
                              updateFragment(index, "title", event.target.value)
                            }
                          />
                        </Field>
                        <Field label="安全预告">
                          <input
                            value={str(fragment.safe_preview)}
                            onChange={(event) =>
                              updateFragment(
                                index,
                                "safe_preview",
                                event.target.value,
                              )
                            }
                          />
                        </Field>
                      </div>
                      <TagEditor
                        tags={stringList(fragment.experience_tags)}
                        onChange={(tags) =>
                          updateFragment(index, "experience_tags", tags)
                        }
                      />
                      <Field label="足迹中的见地讲述（审核后的概括）">
                        <textarea
                          rows={3}
                          maxLength={600}
                          value={str(fragment.footprint_editorial_summary)}
                          onChange={(event) =>
                            updateFragment(
                              index,
                              "footprint_editorial_summary",
                              event.target.value,
                            )
                          }
                          placeholder="仅写可长期保留的事实与故事概括，不写音频版本信息"
                        />
                      </Field>
                      <Field label="可选概括（每行：稳定ID | 文字）">
                        <textarea
                          rows={4}
                          value={formatFootprintSummaryOptions(
                            fragment.footprint_summary_options,
                          )}
                          onChange={(event) =>
                            updateFragment(
                              index,
                              "footprint_summary_options",
                              parseFootprintSummaryOptions(event.target.value),
                            )
                          }
                          placeholder={"noticed-bricks | 我留意到新旧砖缝\ncity-memory | 城市记忆藏在日常细节里"}
                        />
                      </Field>
                      <Field label="耳机旁白（保存时须与文字稿完全一致）">
                        <textarea
                          rows={6}
                          value={str(fragment.narration_script)}
                          onChange={(event) => {
                            updateFragment(
                              index,
                              "narration_script",
                              event.target.value,
                            );
                            updateFragment(
                              index,
                              "transcript",
                              event.target.value,
                            );
                          }}
                        />
                      </Field>
                      <div className="form-grid">
                        <Field label="音频资源">
                          <input
                            list="fragment-audio-assets"
                            value={str(fragment.audio_path)}
                            onChange={(event) =>
                              updateFragment(
                                index,
                                "audio_path",
                                event.target.value,
                              )
                            }
                          />
                        </Field>
                        <Field label="脚本版本">
                          <input
                            value={str(fragment.script_version)}
                            onChange={(event) =>
                              updateFragment(
                                index,
                                "script_version",
                                event.target.value,
                              )
                            }
                          />
                        </Field>
                      </div>
                      <details className="narration-node-tools">
                        <summary>单节点音频纠错（可选）</summary>
                        <NarrationAudition
                          fragmentId={str(fragment.id)}
                          profile={selectedNarrationProfile}
                          hasCurrentOfficialAudio={Boolean(
                            narrationCoverage?.complete_fragment_ids.includes(str(fragment.id)),
                          )}
                          request={request}
                          setNotice={setNotice}
                          onApproved={() => {
                            void load(routeId);
                            void loadNarrationCoverage();
                          }}
                        />
                      </details>
                      <div className="fragment-subhead">WGS-84 定位触发</div>
                      <div className="form-grid three">
                        <Field label="纬度">
                          <input
                            type="number"
                            step="any"
                            value={num(region.latitude, 0)}
                            onChange={(event) =>
                              updateNestedFragment(
                                index,
                                "trigger_region",
                                "latitude",
                                Number(event.target.value),
                              )
                            }
                          />
                        </Field>
                        <Field label="经度">
                          <input
                            type="number"
                            step="any"
                            value={num(region.longitude, 0)}
                            onChange={(event) =>
                              updateNestedFragment(
                                index,
                                "trigger_region",
                                "longitude",
                                Number(event.target.value),
                              )
                            }
                          />
                        </Field>
                        <Field label="进入 / 离开半径">
                          <div className="inline-fields">
                            <input
                              type="number"
                              value={num(region.entry_radius_m, 60)}
                              onChange={(event) =>
                                updateNestedFragment(
                                  index,
                                  "trigger_region",
                                  "entry_radius_m",
                                  Number(event.target.value),
                                )
                              }
                            />
                            <input
                              type="number"
                              value={num(region.exit_radius_m, 90)}
                              onChange={(event) =>
                                updateNestedFragment(
                                  index,
                                  "trigger_region",
                                  "exit_radius_m",
                                  Number(event.target.value),
                                )
                              }
                            />
                          </div>
                        </Field>
                      </div>
                      <Field label="坐标来源">
                        <input
                          value={str(region.coordinate_source)}
                          onChange={(event) =>
                            updateNestedFragment(
                              index,
                              "trigger_region",
                              "coordinate_source",
                              event.target.value,
                            )
                          }
                        />
                      </Field>
                      {Object.keys(mission).length > 0 && (
                        <>
                          <div className="fragment-subhead">现场照片留念（不阻塞路线）</div>
                          <Field label="拍摄提示">
                            <textarea
                              rows={2}
                              value={str(mission.prompt)}
                              onChange={(event) =>
                                updateNestedFragment(
                                  index,
                                  "photo_mission",
                                  "prompt",
                                  event.target.value,
                                )
                              }
                            />
                          </Field>
                          <div className="form-grid three">
                            <Field label="安全站位 / 经典机位">
                              <textarea
                                rows={3}
                                placeholder="例如：站在观景平台内侧，距栏杆一步，避开车行道"
                                value={str(mission.vantage_point)}
                                onChange={(event) =>
                                  updateNestedFragment(
                                    index,
                                    "photo_mission",
                                    "vantage_point",
                                    event.target.value,
                                  )
                                }
                              />
                            </Field>
                            <Field label="拍摄朝向">
                              <textarea
                                rows={3}
                                placeholder="例如：镜头朝东南，对准钟楼正面"
                                value={str(mission.shooting_direction)}
                                onChange={(event) =>
                                  updateNestedFragment(
                                    index,
                                    "photo_mission",
                                    "shooting_direction",
                                    event.target.value,
                                  )
                                }
                              />
                            </Field>
                            <Field label="构图建议">
                              <textarea
                                rows={3}
                                placeholder="例如：让拱门占画面上三分之一，人物放在右下交点"
                                value={str(mission.composition_tip)}
                                onChange={(event) =>
                                  updateNestedFragment(
                                    index,
                                    "photo_mission",
                                    "composition_tip",
                                    event.target.value,
                                  )
                                }
                              />
                            </Field>
                          </div>
                          <Field label="安全提醒">
                            <input
                              value={str(mission.safety_copy)}
                              onChange={(event) =>
                                updateNestedFragment(
                                  index,
                                  "photo_mission",
                                  "safety_copy",
                                  event.target.value,
                                )
                              }
                            />
                          </Field>
                        </>
                      )}
                    </article>
                  );
                })}
                <article className="panel reference-editor">
                  <div className="panel-heading">
                    <div>
                      <p className="eyebrow">SOURCES & CLAIMS</p>
                      <h2>史实来源与主张</h2>
                    </div>
                  </div>
                  <div className="reference-section">
                    <h3>来源</h3>
                    {graph.sources.map((item, index) => (
                      <div className="reference-row" key={str(item.id)}>
                        <small>{str(item.id)}</small>
                        <div className="form-grid">
                          <Field label="来源标题">
                            <input
                              value={str(item.title)}
                              onChange={(event) =>
                                updateCollection(
                                  "sources",
                                  index,
                                  "title",
                                  event.target.value,
                                )
                              }
                            />
                          </Field>
                          <Field label="发布机构">
                            <input
                              value={str(item.publisher)}
                              onChange={(event) =>
                                updateCollection(
                                  "sources",
                                  index,
                                  "publisher",
                                  event.target.value,
                                )
                              }
                            />
                          </Field>
                        </div>
                        <Field label="链接">
                          <input
                            value={str(item.url)}
                            onChange={(event) =>
                              updateCollection(
                                "sources",
                                index,
                                "url",
                                event.target.value,
                              )
                            }
                          />
                        </Field>
                      </div>
                    ))}
                  </div>
                  <div className="reference-section">
                    <h3>史实主张</h3>
                    {graph.claims.map((item, index) => (
                      <div className="reference-row" key={str(item.id)}>
                        <small>{str(item.id)}</small>
                        <Field label="主张正文">
                          <textarea
                            rows={2}
                            value={str(item.canonical_text)}
                            onChange={(event) =>
                              updateCollection(
                                "claims",
                                index,
                                "canonical_text",
                                event.target.value,
                              )
                            }
                          />
                        </Field>
                        <Field label="来源 ID（逗号分隔）">
                          <input
                            value={
                              Array.isArray(item.source_ids)
                                ? item.source_ids.join(", ")
                                : ""
                            }
                            onChange={(event) =>
                              updateCollection(
                                "claims",
                                index,
                                "source_ids",
                                event.target.value
                                  .split(",")
                                  .map((value) => value.trim())
                                  .filter(Boolean),
                              )
                            }
                          />
                        </Field>
                      </div>
                    ))}
                  </div>
                </article>
              </div>
            </div>
          )}
          <datalist id="fragment-audio-assets">
            {media
              .filter((item) => item.mime_type.startsWith("audio/"))
              .map((item) => (
                <option value={item.storage_path} key={item.key}>
                  {item.key}
                </option>
              ))}
          </datalist>
          {validation && (
            <article
              className={`panel validation-panel ${validation.valid ? "valid" : "invalid"}`}
            >
              <div>
                <p className="eyebrow">PUBLICATION GATE</p>
                <h2>
                  {validation.valid
                    ? "内容校验通过"
                    : `${validation.errors.length} 个问题阻止发布`}
                </h2>
              </div>
              <div className="validation-columns">
                <IssueList
                  title="错误"
                  rows={validation.errors}
                  empty="无阻断问题"
                />
                <IssueList
                  title="提醒"
                  rows={validation.warnings}
                  empty="无提醒"
                />
              </div>
            </article>
          )}
          <div className="publish-bar">
            <span>仅“已发布”且有发布时间的内容会在客户端展示。</span>
            <button
              className="ghost-button"
              onClick={() => void validate()}
              disabled={busy}
            >
              校验数据库版本
            </button>
            <button
              className="ghost-button"
              onClick={() => void save()}
              disabled={busy || str(graph.route.content_status) === "published"}
            >
              {busy ? "处理中…" : "保存内容"}
            </button>
            {["draft", "in_review", "verified", "published"].includes(
              str(graph.route.content_status),
            ) && (
              <button
                className="primary-button"
                onClick={() => void advanceLifecycle()}
                disabled={busy}
              >
                {lifecycleAction(str(graph.route.content_status))}
              </button>
            )}
          </div>
        </>
      )}
    </section>
  );
}

function NarrationProfilePanel({
  routeId,
  profiles,
  selectedProfileId,
  coverage,
  request,
  setNotice,
  onSelect,
  onChanged,
}: {
  routeId: string;
  profiles: NarrationProfileView[];
  selectedProfileId: string;
  coverage: NarrationCoverage | null;
  request: <T>(p: string, i?: RequestInit) => Promise<T>;
  setNotice: (x: string) => void;
  onSelect: (id: string) => void;
  onChanged: () => void;
}) {
  const selected = profiles.find((item) => item.id === selectedProfileId);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [batchBusy, setBatchBusy] = useState(false);
  const [credentialsConfigured, setCredentialsConfigured] = useState(false);
  const [batchResult, setBatchResult] = useState<NarrationBatchResult | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Partial<NarrationProfileView>>>({});

  useEffect(() => {
    let active = true;
    request<NarrationConfigView>("/narration/config")
      .then((config) => {
        if (active) setCredentialsConfigured(config.credentials_configured);
      })
      .catch((error) => {
        if (active) setNotice(error instanceof Error ? error.message : "语音服务配置读取失败");
      });
    return () => { active = false; };
  }, [request, setNotice]);

  async function mutate(path: string, init: RequestInit, success: string) {
    setBusy(true);
    try {
      const value = await request<NarrationProfileView | { profile: NarrationProfileView }>(path, init);
      const profile = "profile" in value ? value.profile : value;
      onSelect(profile.id);
      setNotice(success);
      onChanged();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "音色操作失败");
    } finally {
      setBusy(false);
    }
  }

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    await mutate("/narration/profiles", {
      method: "POST",
      body: JSON.stringify({
        slug: data.get("slug"),
        display_name: data.get("display_name"),
        description: data.get("description"),
        voice_id: data.get("voice_id"),
        display_order: Number(data.get("display_order") || 10),
      }),
    }, "新音色档案已创建，请为每条线索生成并批准音频");
    setCreating(false);
  }

  if (!selected) return null;
  const draft = drafts[selected.id] || selected;
  const updateDraft = (changes: Partial<NarrationProfileView>) =>
    setDrafts((current) => ({
      ...current,
      [selected.id]: { ...(current[selected.id] || selected), ...changes },
    }));

  async function generateRoute(regenerateAll: boolean) {
    setBatchBusy(true);
    setBatchResult(null);
    try {
      const editableKeys: Array<keyof NarrationProfileView> = [
        "display_name", "description", "voice_id", "emotion", "speed", "pitch", "display_order",
      ];
      const changed = editableKeys.some((key) => draft[key] !== selected[key]);
      if (changed) {
        await request<NarrationProfileView>(`/narration/profiles/${selected.id}`, {
          method: "PUT",
          body: JSON.stringify(draft),
        });
      }
      const value = await request<NarrationBatchResult>(
        `/routes/${routeId}/narration/generate`,
        {
          method: "POST",
          body: JSON.stringify({
            profile_id: selected.id,
            regenerate_all: regenerateAll,
          }),
        },
      );
      setBatchResult(value);
      if (value.failed_count) {
        setNotice(`已保存 ${value.generated_count} 条，${value.failed_count} 条失败；可直接重试失败节点`);
      } else if (value.generated_count) {
        setNotice(
          value.profile.status === "published"
            ? `整条路线已生成并保存 ${value.generated_count} 条正式音频，新音频已立即发布生效`
            : `整条路线已生成并保存 ${value.generated_count} 条正式音频，请点击“发布音色”上线`,
        );
      } else {
        setNotice("当前音色已经覆盖整条路线，无需重复生成");
      }
      onChanged();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "整条路线音频生成失败");
    } finally {
      setBatchBusy(false);
    }
  }

  const incomplete = (coverage?.missing.length ?? 0) + (coverage?.stale.length ?? 0);
  return (
    <article className="panel narration-profile-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">NARRATION VOICES</p>
          <h2>路线讲述音色</h2>
          <p>只有覆盖全部当前文字稿的已发布音色，才会出现在客户端选择器。</p>
        </div>
        <button className="ghost-button" onClick={() => setCreating((value) => !value)}>
          {creating ? "取消新建" : "新建音色"}
        </button>
      </div>
      {creating && (
        <form className="voice-create-form" onSubmit={(event) => void create(event)}>
          <label className="field"><span>英文标识</span><input name="slug" required placeholder="warm-storyteller" /></label>
          <label className="field"><span>客户端名称</span><input name="display_name" required placeholder="温柔讲述者" /></label>
          <label className="field"><span>Voice ID</span><input name="voice_id" required placeholder="供应商音色 ID" /></label>
          <label className="field"><span>排序</span><input name="display_order" type="number" defaultValue="10" /></label>
          <label className="field full"><span>客户端风格说明</span><input name="description" placeholder="温暖、克制，适合边走边听" /></label>
          <button className="primary-button" disabled={busy}>创建草稿</button>
        </form>
      )}
      <div className="voice-profile-layout">
        <div className="voice-profile-list" role="listbox" aria-label="音色档案">
          {profiles.map((profile) => (
            <button
              key={profile.id}
              className={profile.id === selectedProfileId ? "active" : ""}
              onClick={() => onSelect(profile.id)}
              role="option"
              aria-selected={profile.id === selectedProfileId}
            >
              <span>{profile.display_name}</span>
              <small>{profile.status}{profile.is_default ? " · 默认" : ""}</small>
            </button>
          ))}
        </div>
        <div className="voice-profile-editor">
          <div className="voice-coverage">
            <div><strong>{coverage?.complete_count ?? 0}/{coverage?.total ?? 0}</strong><span>当前文字稿覆盖</span></div>
            <StatusTag status={coverage?.ready ? "published" : "in_review"} />
            {!!coverage?.missing.length && <small>缺少：{coverage.missing.map((item) => item.title).join("、")}</small>}
            {!!coverage?.stale.length && <small>已过期：{coverage.stale.map((item) => item.title).join("、")}</small>}
          </div>
          <div className="form-grid three">
            <Field label="客户端名称"><input value={str(draft.display_name)} onChange={(event) => updateDraft({ display_name: event.target.value })} /></Field>
            <Field label="Voice ID"><input value={str(draft.voice_id)} onChange={(event) => updateDraft({ voice_id: event.target.value })} /></Field>
            <Field label="排序"><input type="number" value={num(draft.display_order, 0)} onChange={(event) => updateDraft({ display_order: Number(event.target.value) })} /></Field>
            <Field label="默认情绪"><input value={str(draft.emotion)} onChange={(event) => updateDraft({ emotion: event.target.value })} /></Field>
            <Field label="默认语速"><input type="number" min="0.5" max="2" step="0.01" value={num(draft.speed, 1)} onChange={(event) => updateDraft({ speed: Number(event.target.value) })} /></Field>
            <Field label="默认音调"><input type="number" min="-12" max="12" value={num(draft.pitch, 0)} onChange={(event) => updateDraft({ pitch: Number(event.target.value) })} /></Field>
          </div>
          <Field label="客户端风格说明"><textarea rows={2} value={str(draft.description)} onChange={(event) => updateDraft({ description: event.target.value })} /></Field>
          <section className="voice-route-generator">
            <div>
              <p className="eyebrow">ONE-CLICK ROUTE AUDIO</p>
              <h3>一次生成整条路线</h3>
              <p>
                当前选择“{selected.display_name}”。系统会用同一音色为全部故事节点生成并直接保存正式音频；客户端只会展示完整覆盖且已发布的音色。
              </p>
            </div>
            <div className="voice-route-generator-actions">
              <button
                className="primary-button"
                disabled={batchBusy || !credentialsConfigured || !routeId}
                onClick={() => void generateRoute(coverage?.ready || !incomplete)}
              >
                {batchBusy
                  ? "正在生成整条路线…"
                  : incomplete
                    ? `生成缺失的 ${incomplete} 个节点`
                    : coverage?.ready
                      ? "重新生成整条路线正式音频"
                      : "一键生成整条路线正式音频"}
              </button>
              {incomplete > 0 && coverage && coverage.complete_count > 0 && (
                <button
                  className="ghost-button"
                  disabled={batchBusy || !credentialsConfigured}
                  onClick={() => void generateRoute(true)}
                >
                  重新生成全部节点
                </button>
              )}
            </div>
            {!credentialsConfigured && <strong className="voice-route-warning">请先在服务器配置 MiniMax 凭证</strong>}
            {batchResult && (
              <div className="voice-route-result">
                <strong>
                  保存 {batchResult.generated_count} · 失败 {batchResult.failed_count} · 跳过 {batchResult.skipped_count}
                </strong>
                <ul>
                  {batchResult.results.map((item) => (
                    <li key={item.fragment_id} className={item.status}>
                      <span>{item.title}</span>
                      <small>
                        {item.status === "saved"
                          ? "正式音频已保存"
                          : item.status === "skipped"
                            ? "已有当前版本"
                            : `失败：${narrationErrorMessage(item.error_code)}`}
                      </small>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>
          <div className="voice-profile-actions">
            <button className="ghost-button" disabled={busy} onClick={() => void mutate(`/narration/profiles/${selected.id}`, { method: "PUT", body: JSON.stringify(draft) }, "音色档案已保存")}>保存档案</button>
            {selected.status === "published" ? (
              <div className="voice-published-state" role="status">
                <strong>✓ 已发布到客户端</strong>
                <small>该音色重新生成并保存后会立即生效，不需要重复点击发布。</small>
              </div>
            ) : (
              <button
                className="primary-button"
                disabled={busy || !coverage?.ready}
                title={coverage?.ready ? "将完整音色发布到客户端" : "必须先生成并保存全部故事节点"}
                onClick={() => void mutate(`/narration/profiles/${selected.id}/publish`, { method: "POST", body: JSON.stringify({ route_id: routeId }) }, "音色已发布到客户端")}
              >
                {coverage?.ready ? "发布音色到客户端" : `还缺 ${incomplete} 个节点，暂不能发布`}
              </button>
            )}
            <button className="ghost-button" disabled={busy || selected.is_default || selected.status !== "published"} onClick={() => void mutate(`/narration/profiles/${selected.id}/set-default`, { method: "POST" }, "已设为路线默认音色")}>设为默认</button>
            <button className="danger-link" disabled={busy || selected.is_default} onClick={() => void mutate(`/narration/profiles/${selected.id}/archive`, { method: "POST" }, "音色已归档")}>归档</button>
          </div>
        </div>
      </div>
    </article>
  );
}

function NarrationAudition({
  fragmentId,
  profile,
  hasCurrentOfficialAudio,
  request,
  setNotice,
  onApproved,
}: {
  fragmentId: string;
  profile?: NarrationProfileView;
  hasCurrentOfficialAudio: boolean;
  request: <T>(p: string, i?: RequestInit) => Promise<T>;
  setNotice: (x: string) => void;
  onApproved: () => void;
}) {
  const [previews, setPreviews] = useState<NarrationPreviewView[]>([]);
  const [audioUrls, setAudioUrls] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [credentialsConfigured, setCredentialsConfigured] = useState(false);
  const [voiceId, setVoiceId] = useState("");
  const [emotions, setEmotions] = useState(["neutral", "happy"]);
  const [variants, setVariants] = useState<NarrationVariant[]>([]);
  const [savedPreviewId, setSavedPreviewId] = useState<string | null>(null);
  const objectUrls = useRef<string[]>([]);

  useEffect(() => () => objectUrls.current.forEach(URL.revokeObjectURL), []);

  useEffect(() => {
    let active = true;
    request<NarrationConfigView>("/narration/config")
      .then((config) => {
        if (!active) return;
        setProvider(profile?.provider || config.provider);
        setModel(profile?.model || config.model);
        setCredentialsConfigured(config.credentials_configured);
        setVoiceId(profile?.voice_id || config.default_voice_id);
        setEmotions(config.supported_emotions);
        setVariants(config.presets.map((item) => profile ? {
          ...item,
          emotion: profile.emotion || item.emotion,
          speed: profile.speed,
          pitch: profile.pitch,
        } : item));
      })
      .catch((error) => {
        if (active) setNotice(error instanceof Error ? error.message : "音色配置加载失败");
      });
    return () => { active = false; };
  }, [profile, request, setNotice]);

  function updateVariant(index: number, changes: Partial<NarrationVariant>) {
    setVariants((current) => current.map((item, itemIndex) =>
      itemIndex === index ? { ...item, ...changes } : item));
  }

  async function generate() {
    setBusy(true);
    try {
      objectUrls.current.forEach(URL.revokeObjectURL);
      objectUrls.current = [];
      setAudioUrls({});
      setSavedPreviewId(null);
      const value = await request<{ previews: NarrationPreviewView[] }>(
        `/fragments/${fragmentId}/narration/previews`,
        {
          method: "POST",
          body: JSON.stringify({
            profile_id: profile?.id,
            variants: variants.map((variant) => ({ ...variant, voice_id: voiceId.trim() })),
          }),
        },
      );
      setPreviews(value.previews);
      const readyItems = value.previews.filter((item) => item.status === "ready");
      const errorCodes = new Set(
        value.previews.map((item) => item.error_code).filter(Boolean),
      );
      if (readyItems.length) {
        setNotice(
          `已生成并临时保存 ${readyItems.length} 个试听版本；请试听后选择一个保存为正式音频`,
        );
        void Promise.all(readyItems.map((item) => loadAudio(item, true)));
      } else if (errorCodes.has("credentials_unavailable")) {
        setNotice("MiniMax 凭证未配置，未生成任何试听音频");
      } else {
        setNotice(`旁白生成失败：${Array.from(errorCodes).join("、") || "语音服务不可用"}`);
      }
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "旁白生成失败");
    } finally {
      setBusy(false);
    }
  }

  async function loadAudio(item: NarrationPreviewView, quiet = false) {
    if (!item.playback_path || audioUrls[item.id]) return;
    try {
      const data = await request<ArrayBuffer>(item.playback_path);
      const url = URL.createObjectURL(new Blob([data], { type: "audio/mpeg" }));
      objectUrls.current.push(url);
      setAudioUrls((current) => ({
        ...current,
        [item.id]: url,
      }));
    } catch (error) {
      if (!quiet) {
        setNotice(error instanceof Error ? error.message : "试听加载失败");
      }
    }
  }

  async function approve(item: NarrationPreviewView) {
    setBusy(true);
    try {
      await request(`/narration/previews/${item.id}/approve`, { method: "POST" });
      setPreviews((current) => current.map((row) => {
        if (row.id === item.id) return { ...row, status: "approved" };
        return row.status === "approved" ? { ...row, status: "ready" } : row;
      }));
      setSavedPreviewId(item.id);
      setNotice("正式音频已保存并绑定当前文字稿；路线音色覆盖进度已更新");
      onApproved();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "批准旁白失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="narration-audition">
      <div className="fragment-subhead">情感旁白试听 · {profile?.display_name || "默认音色"}</div>
      <div className={`narration-save-state ${hasCurrentOfficialAudio ? "saved" : "missing"}`}>
        <strong>{hasCurrentOfficialAudio ? "当前线索已保存正式音频" : "当前线索尚未保存正式音频"}</strong>
        <span>
          {hasCurrentOfficialAudio
            ? "重新生成并保存其他版本会替换这个音色在当前线索下的正式音频。"
            : "生成只会创建临时试听；必须选中一个版本并保存，才会计入路线覆盖。"}
        </span>
      </div>
      <ol className="narration-workflow" aria-label="旁白保存流程">
        <li><b>1</b><span><strong>生成临时试听</strong><small>调整音色、情绪、语速和音调</small></span></li>
        <li><b>2</b><span><strong>试听并保存一个版本</strong><small>点击“选用并保存为正式音频”</small></span></li>
        <li><b>3</b><span><strong>完成整条路线后发布音色</strong><small>返回上方音色面板执行发布</small></span></li>
      </ol>
      <p className="narration-storage-note">
        试听版本是私有临时文件，默认保留 24 小时，不会自动上线；保存后的正式音频会进入公共媒体存储并绑定当前文字稿。
      </p>
      <div className="narration-provider-line">
        <span>服务：{provider || "加载中"}</span>
        <span>模型：{model || "加载中"}</span>
        <span className={credentialsConfigured ? "configured" : "unconfigured"}>
          {credentialsConfigured ? "语音凭证已配置" : "语音凭证未配置"}
        </span>
      </div>
      <label className="field narration-voice-field">
        <span>音色 Voice ID</span>
        <input
          aria-label="音色 Voice ID"
          value={voiceId}
          onChange={(event) => setVoiceId(event.target.value)}
          placeholder="例如 Chinese (Mandarin)_Gentleman"
        />
      </label>
      <div className="narration-settings-grid">
        {variants.map((variant, index) => <article key={`${variant.label}-${index}`}>
          <strong>{variant.label}</strong>
          <label className="field">
            <span>情绪</span>
            <select value={variant.emotion} onChange={(event) => updateVariant(index, { emotion: event.target.value })}>
              {emotions.map((emotion) => <option key={emotion} value={emotion}>{emotion}</option>)}
            </select>
          </label>
          <label className="field">
            <span>语速</span>
            <input type="number" min="0.5" max="2" step="0.01" value={variant.speed} onChange={(event) => updateVariant(index, { speed: Number(event.target.value) })} />
          </label>
          <label className="field">
            <span>音调</span>
            <input type="number" min="-12" max="12" step="1" value={variant.pitch} onChange={(event) => updateVariant(index, { pitch: Number(event.target.value) })} />
          </label>
        </article>)}
      </div>
      <button className="ghost-button" onClick={() => void generate()} disabled={busy || !fragmentId || !voiceId.trim() || variants.length < 3 || !credentialsConfigured}>
        {busy ? "处理中…" : "生成 3 个临时试听版本"}
      </button>
      {previews.length > 0 && <div className="narration-preview-grid">
        {previews.map((item) => <article key={item.id} className={savedPreviewId === item.id || item.status === "approved" ? "official" : ""}>
          <div className="narration-preview-heading">
            <strong>{str(item.metadata.label) || item.emotion}</strong>
            {(savedPreviewId === item.id || item.status === "approved") && <span>正式音频</span>}
          </div>
          <small>{item.voice_id} · {item.emotion} · {item.speed}× · pitch {item.pitch}</small>
          {item.status === "failed" ? <em>暂不可用：{narrationErrorMessage(item.error_code)}</em> : <>
            {!audioUrls[item.id] ? <button onClick={() => void loadAudio(item)}>播放器加载失败，点击重试</button> : <>
              {/* eslint-disable-next-line jsx-a11y/media-has-caption -- the exact transcript is visible in the fragment editor */}
              <audio controls src={audioUrls[item.id]} aria-label={`${str(item.metadata.label) || item.emotion}旁白试听`} />
            </>}
            <button
              className="save-official-audio"
              onClick={() => void approve(item)}
              disabled={busy || item.status === "approved"}
            >
              {item.status === "approved"
                ? "已保存为正式音频"
                : hasCurrentOfficialAudio || savedPreviewId
                  ? "改用此版本并替换正式音频"
                  : "选用并保存为正式音频"}
            </button>
          </>}
        </article>)}
      </div>}
    </section>
  );
}

function IssueList({
  title,
  rows,
  empty,
}: {
  title: string;
  rows: ValidationIssue[];
  empty: string;
}) {
  return (
    <div>
      <h3>{title}</h3>
      {rows.length ? (
        <ul>
          {rows.map((item, index) => (
            <li key={`${item.path}-${item.code}-${index}`}>
              <code>{item.path}</code>
              <span>{item.message}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p>{empty}</p>
      )}
    </div>
  );
}

function CityStoryCatalogWorkspace({
  cities,
  request,
  setNotice,
}: {
  cities: City[];
  request: <T>(p: string, i?: RequestInit) => Promise<T>;
  setNotice: (x: string) => void;
}) {
  const [items, setItems] = useState<StoryCatalogView[]>([]);
  const [cityId, setCityId] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const selectedCity = cities.find((city) => city.id === cityId);
  const selected = items.find((item) => item.id === editingId);
  const cityItems = items.filter((item) => item.city_id === cityId);

  const loadCatalog = useCallback(async () => {
    try {
      setItems(await request<StoryCatalogView[]>("/story-catalog"));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "城市故事读取失败");
    }
  }, [request, setNotice]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadCatalog(), 0);
    return () => window.clearTimeout(timer);
  }, [loadCatalog]);

  async function saveStory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!cityId) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    try {
      const saved = await request<StoryCatalogView>(
        selected ? `/story-catalog/${selected.id}` : "/story-catalog",
        {
          method: selected ? "PUT" : "POST",
          body: JSON.stringify({
            city_id: cityId,
            title: String(form.get("title") || "").trim(),
            story_content: String(form.get("story_content") || "").trim(),
            expected_version: selected?.version,
          }),
        },
      );
      await loadCatalog();
      setEditingId(saved.id);
      setCreating(false);
      setNotice("城市故事已保存");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "城市故事保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function transition(action: string) {
    if (!selected) return;
    try {
      await request(`/story-catalog/${selected.id}/${action}`, { method: "POST" });
      await loadCatalog();
      setNotice(action === "publish" ? "城市故事已发布" : "故事状态已更新");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "故事状态更新失败");
    }
  }

  if (!selectedCity) {
    return (
      <section className="city-story-city-grid">
        {cities.map((city) => {
          const count = items.filter((item) => item.city_id === city.id).length;
          return (
            <button key={city.id} className="panel city-story-city-card" onClick={() => setCityId(city.id)}>
              <span className="city-story-city-cover">{city.hero_image ? <img src={city.hero_image} alt="" /> : city.name.slice(0, 1)}</span>
              <span><strong>{city.name}</strong><small>{count ? `${count} 个故事` : "还没有故事"}</small></span>
              <i>进入 →</i>
            </button>
          );
        })}
        {!cities.length && <TableEmpty text="请先添加城市" />}
      </section>
    );
  }

  return (
    <section className="city-story-workspace">
      <article className="panel city-story-heading">
        <div><button className="text-button" onClick={() => { setCityId(""); setEditingId(null); setCreating(false); }}>← 返回城市</button><p className="eyebrow">CITY STORIES</p><h2>{selectedCity.name} · 城市故事</h2><p>这里只配置标题和故事内容。</p></div>
        <button className="primary-button" onClick={() => { setEditingId(null); setCreating(true); }}>＋ 添加故事</button>
      </article>
      <div className="city-story-layout">
        <div className="city-story-list">
          {cityItems.map((item) => (
            <button key={item.id} className={item.id === editingId ? "panel city-story-card selected" : "panel city-story-card"} onClick={() => { setEditingId(item.id); setCreating(false); }}>
              <span><strong>{item.title}</strong><small>{storyStatusLabel(item.status)}</small></span>
              <p>{item.story_content || str(item.source.transcript)}</p>
            </button>
          ))}
          {!cityItems.length && <TableEmpty text="这个城市还没有故事，点击添加故事" />}
        </div>
        {(selected || creating) ? (
          <form key={selected?.id || "new"} className="panel city-story-editor" onSubmit={saveStory}>
            <div><p className="eyebrow">STORY EDITOR</p><h2>{selected ? "编辑故事" : "添加故事"}</h2><small>所属城市：{selectedCity.name}</small></div>
            <Field label="标题"><input name="title" defaultValue={selected?.title || ""} required /></Field>
            <Field label="故事内容"><textarea name="story_content" rows={16} defaultValue={selected?.story_content || str(selected?.source.transcript)} required /></Field>
            {selected?.blockers.length ? <div className="story-blockers"><strong>发布前提示</strong><ul>{selected.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul></div> : null}
            <div className="import-actions">
              <button className="primary-button" disabled={busy}>{busy ? "保存中…" : "保存故事"}</button>
              {selected?.status === "draft" && <button type="button" onClick={() => void transition("submit-review")}>提交审核</button>}
              {selected?.status === "in_review" && <button type="button" onClick={() => void transition("verify")}>通过审核</button>}
              {selected?.status === "verified" && <button type="button" disabled={!selected.ready_to_publish} onClick={() => void transition("publish")}>发布</button>}
              {selected?.status === "published" && <button type="button" onClick={() => void transition("withdraw")}>撤回</button>}
            </div>
          </form>
        ) : (
          <article className="panel city-story-editor-empty"><span>故</span><p>选择一个故事编辑，或添加新故事。</p></article>
        )}
      </div>
    </section>
  );
}

// Legacy rollback surface; the active city-first UI is CityStoryCatalogWorkspace.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function LegacyCityStoryCatalogWorkspace({
  cities,
  request,
  setNotice,
}: {
  cities: City[];
  request: <T>(p: string, i?: RequestInit) => Promise<T>;
  setNotice: (x: string) => void;
}) {
  const [items, setItems] = useState<StoryCatalogView[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [homeCityId, setHomeCityId] = useState(cities[0]?.id || "");
  const [homePreview, setHomePreview] = useState<Data | null>(null);
  const [busy, setBusy] = useState(false);
  const selected = items.find((item) => item.id === selectedId);

  const loadCatalog = useCallback(async () => {
    try {
      const rows = await request<StoryCatalogView[]>("/story-catalog");
      setItems(rows);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "城市故事目录读取失败");
    }
  }, [request, setNotice]);
  useEffect(() => {
    const timer = window.setTimeout(() => void loadCatalog(), 0);
    return () => window.clearTimeout(timer);
  }, [loadCatalog]);

  async function saveStory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    try {
      const form = new FormData(event.currentTarget);
      const payload = {
        expected_version: selected?.version,
        city_id: String(form.get("city_id") || ""),
        source_kind: String(form.get("source_kind") || ""),
        source_id: String(form.get("source_id") || ""),
        title: String(form.get("title") || ""),
        summary: String(form.get("summary") || ""),
        cover_image: String(form.get("cover_image") || ""),
        district: String(form.get("district") || "") || null,
        themes: parseTagText(String(form.get("themes") || "")),
        point_ids: parseTagText(String(form.get("point_ids") || "")),
        content_type: String(form.get("content_type") || ""),
        place_context: String(form.get("place_context") || ""),
        observable_detail: String(form.get("observable_detail") || ""),
        attention_hint: String(form.get("attention_hint") || "") || null,
        fact_status: String(form.get("fact_status") || "documented"),
        review_status: String(form.get("review_status") || "in_review"),
        sources: parseJsonArray(form, "sources"),
        related_stories: parseJsonArray(form, "related_stories"),
        variants: parseJsonArray(form, "variants"),
        placements: parseJsonArray(form, "placements"),
      };
      const saved = await request<StoryCatalogView>(
        selected ? `/story-catalog/${selected.id}` : "/story-catalog",
        { method: selected ? "PUT" : "POST", body: JSON.stringify(payload) },
      );
      await loadCatalog();
      setSelectedId(saved.id);
      setNotice("城市故事已保存为草稿");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "城市故事保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function transitionStory(action: string) {
    if (!selected) return;
    try {
      await request(`/story-catalog/${selected.id}/${action}`, { method: "POST" });
      await loadCatalog();
      setNotice(action === "publish" ? "城市故事已发布" : "状态已更新");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "状态更新失败");
    }
  }

  async function loadHomePreview() {
    if (!homeCityId) return;
    try {
      setHomePreview(await request<Data>(`/cities/${homeCityId}/home-story-preview`));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "首页模块预览失败");
    }
  }

  return (
    <div className="resource-grid">
      <ResourcePanel eyebrow="CANONICAL CATALOG" title="共享故事目录">
        <div className="form-grid">
          <Field label="选择已有目录项">
            <select value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
              <option value="">＋ 新建目录项</option>
              {items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title} · {storyStatusLabel(item.status)}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <form key={selected?.id || "new"} onSubmit={saveStory} className="form-grid">
          <Field label="所属城市">
            <select name="city_id" defaultValue={selected?.city_id || ""} required>
              <option value="">请选择</option>
              {cities.map((city) => <option key={city.id} value={city.id}>{city.name}</option>)}
            </select>
          </Field>
          <Field label="规范来源类型">
            <select name="source_kind" defaultValue={selected?.source_kind || "story_arc"}>
              <option value="story_arc">完整故事</option>
              <option value="story_fragment">现场故事片段</option>
            </select>
          </Field>
          <Field label="规范来源 ID">
            <input name="source_id" defaultValue={selected?.source_id || ""} required />
          </Field>
          <Field label="内容类型（支持后台新增值）">
            <input name="content_type" defaultValue={selected?.content_type || "街角故事"} required />
          </Field>
          <Field label="标题"><input name="title" defaultValue={selected?.title || ""} required /></Field>
          <Field label="简介"><textarea name="summary" rows={3} defaultValue={selected?.summary || ""} required /></Field>
          <Field label="封面路径"><input name="cover_image" defaultValue={selected?.cover_image || ""} required /></Field>
          <Field label="街区"><input name="district" defaultValue={selected?.district || ""} /></Field>
          <Field label="主题（逗号或换行分隔）"><textarea name="themes" rows={2} defaultValue={(selected?.themes || []).join("，")} /></Field>
          <Field label="相关点位 ID"><textarea name="point_ids" rows={2} defaultValue={(selected?.point_ids || []).join("，")} /></Field>
          <Field label="城市 / 地点背景"><textarea name="place_context" rows={3} defaultValue={selected?.place_context || ""} required /></Field>
          <Field label="可观察的现实细节"><textarea name="observable_detail" rows={3} defaultValue={selected?.observable_detail || ""} required /></Field>
          <Field label="现场留意提示（可选，不是答题）"><textarea name="attention_hint" rows={2} defaultValue={selected?.attention_hint || ""} /></Field>
          <Field label="事实状态"><input name="fact_status" defaultValue={selected?.fact_status || "documented"} /></Field>
          <Field label="审核状态"><select name="review_status" defaultValue={selected?.review_status || "in_review"}><option value="in_review">审核中</option><option value="reviewed">已审核</option><option value="disputed">有争议</option></select></Field>
          <Field label="来源 JSON 数组"><textarea name="sources" rows={4} defaultValue={JSON.stringify(selected?.sources || [], null, 2)} /></Field>
          <Field label="相关故事 JSON 数组（顺序仅建议）"><textarea name="related_stories" rows={4} defaultValue={JSON.stringify(selected?.related_stories || [], null, 2)} /></Field>
          <Field label="展示变体 JSON 数组"><textarea name="variants" rows={6} defaultValue={JSON.stringify(selected?.variants || [], null, 2)} placeholder={'[{"role":"short_preview","track_id":"..."}]'} /></Field>
          <Field label="首页 / 出发前位置 JSON 数组"><textarea name="placements" rows={7} defaultValue={JSON.stringify(selected?.placements || [], null, 2)} placeholder={'[{"channel":"home","module_key":"today_city_story","display_order":0}]'} /></Field>
          {selected && (
            <div className="validation-summary">
              <StatusTag status={selected.status} />
              {selected.warnings.map((message) => <p key={message}>提醒：{message}</p>)}
              {selected.blockers.map((message) => <p key={message}>阻塞：{message}</p>)}
              <details><summary>规范来源只读预览</summary><pre>{JSON.stringify(selected.source, null, 2)}</pre></details>
            </div>
          )}
          <div className="import-actions">
            <button className="primary-button" disabled={busy}>{busy ? "保存中…" : "保存草稿"}</button>
            {selected?.status === "draft" && <button type="button" onClick={() => void transitionStory("submit-review")}>提交审核</button>}
            {selected?.status === "in_review" && <button type="button" onClick={() => void transitionStory("verify")}>通过审核</button>}
            {selected?.status === "verified" && <button type="button" onClick={() => void transitionStory("publish")}>发布</button>}
            {selected?.status === "published" && <button type="button" onClick={() => void transitionStory("withdraw")}>撤回</button>}
          </div>
        </form>
      </ResourcePanel>

      <ResourcePanel eyebrow="HOME MODULE PREVIEW" title="五模块预览">
        <Field label="城市">
          <select value={homeCityId} onChange={(event) => setHomeCityId(event.target.value)}>
            {cities.map((city) => <option key={city.id} value={city.id}>{city.name}</option>)}
          </select>
        </Field>
        <button onClick={() => void loadHomePreview()}>刷新草稿 / 发布投影</button>
        {homePreview && <pre>{JSON.stringify(homePreview, null, 2)}</pre>}
      </ResourcePanel>

    </div>
  );
}

function parseJsonArray(form: FormData, field: string): Data[] {
  const raw = String(form.get(field) || "").trim();
  if (!raw) return [];
  const parsed: unknown = JSON.parse(raw);
  if (!Array.isArray(parsed)) throw new Error(`${field} 必须是 JSON 数组`);
  return parsed as Data[];
}

function ImportView({
  request,
  onImported,
  setNotice,
}: {
  request: <T>(p: string, i?: RequestInit) => Promise<T>;
  onImported: () => void;
  setNotice: (x: string) => void;
}) {
  const sample = useMemo(
    () =>
      JSON.stringify(
        {
          schema_version: "1.0",
          package_id: "city-knowledge-sample",
          package_version: "2026.08.23-1",
          entities: {
            cities: [{
              id: "city-hangzhou",
              slug: "hangzhou",
              name: "杭州",
              subtitle: "在水岸与街巷之间漫游",
              hero_image: "images/hangzhou.jpg",
              latitude: 30.2741,
              longitude: 120.1551,
            }],
            routes: [],
            stops: [],
            story_arcs: [],
            story_fragments: [],
            catalog_items: [],
            variants: [],
            placements: [],
            pretrip_guidance: [],
            media: [],
          },
        },
        null,
        2,
      ),
    [],
  );
  const [content, setContent] = useState(sample);
  const [importing, setImporting] = useState(false);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  function readFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setContent(String(reader.result || ""));
    reader.readAsText(file);
  }
  async function submitPreview() {
    setImporting(true);
    setPreview(null);
    try {
      const parsed = JSON.parse(content);
      if (parsed.schema_version === "1.0" && parsed.entities) {
        const form = new FormData();
        form.append(
          "file",
          new File([content], `${parsed.package_id || "content-package"}.json`, {
            type: "application/json",
          }),
        );
        setPreview(
          await request<ImportPreview>("/multi-city-import/preview", {
            method: "POST",
            body: form,
          }),
        );
        setNotice("预检完成；确认前数据库中没有写入内容记录");
      } else if (parsed.package_id && parsed.story_arc) {
        await request("/fragmented-routes/import", {
          method: "POST",
          body: JSON.stringify(parsed),
        });
        onImported();
      } else {
        await request("/import", {
          method: "POST",
          body: JSON.stringify(parsed),
        });
        onImported();
      }
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "导入失败");
    } finally {
      setImporting(false);
    }
  }
  async function confirmImport() {
    if (!preview?.confirmation_token) return;
    setImporting(true);
    try {
      await request("/multi-city-import/confirm", {
        method: "POST",
        body: JSON.stringify({ confirmation_token: preview.confirmation_token }),
      });
      setPreview(null);
      onImported();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "确认导入失败");
    } finally {
      setImporting(false);
    }
  }
  return (
    <section className="import-layout">
      <article className="panel import-editor">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">JSON IMPORT</p>
            <h2>内容数据</h2>
          </div>
          <label className="small-upload">
            读取 JSON
            <input
              type="file"
              accept="application/json,.json"
              onChange={readFile}
            />
          </label>
        </div>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          spellCheck={false}
        />
        <div className="import-actions">
          <button className="ghost-button" onClick={() => setContent(sample)}>
            恢复示例
          </button>
          <button
            className="primary-button"
            onClick={submitPreview}
            disabled={importing}
          >
            {importing ? "处理中…" : "上传并预检"}
          </button>
        </div>
        {preview && (
          <section className="validation-summary" aria-live="polite">
            <h3>预检结果</h3>
            <p>
              新增 {preview.counts.new || 0} · 更新 {preview.counts.updated || 0} ·
              不变 {preview.counts.unchanged || 0} · 冲突 {preview.counts.conflicted || 0} ·
              无效 {preview.counts.invalid || 0}
            </p>
            {preview.problems.length > 0 && (
              <IssueList title="阻塞项" rows={preview.problems} empty="没有阻塞项" />
            )}
            <details>
              <summary>逐项差异（{preview.changes.length}）</summary>
              <ul>
                {preview.changes.map((change) => (
                  <li key={`${change.entity}-${change.id}-${change.path}`}>
                    <code>{change.path}</code> · {change.status}
                    {change.changed_fields.length > 0 && ` · ${change.changed_fields.join("、")}`}
                  </li>
                ))}
              </ul>
            </details>
            <button
              className="primary-button"
              disabled={!preview.can_confirm || importing}
              onClick={() => void confirmImport()}
            >
              确认写入草稿区
            </button>
            {!preview.can_confirm && <p>修复全部阻塞项后重新上传，才能确认导入。</p>}
          </section>
        )}
      </article>
      <aside className="panel import-help">
        <p className="eyebrow">SUPPORTED CONTENT</p>
        <h2>支持内容</h2>
        <ul>
          <li>
            <b>schema_version 1.0 多城市包</b>
            <span>城市、路线、点位、故事、目录位置、出发前提示与受管媒体引用</span>
          </li>
          <li>
            <b>cities / routes</b>
            <span>传统城市、路线与发布状态</span>
          </li>
          <li>
            <b>stops</b>
            <span>地点、故事、观察提示</span>
          </li>
          <li>
            <b>challenges</b>
            <span>问题、选项、答案与解析</span>
          </li>
        </ul>
        <p>
          新格式必须先预检再确认，确认时整包事务写入且一律进入草稿；不会绕过审核或发布。
          旧的单路线碎片包和传统 cities/routes/stops 文件仍保持原接口兼容。
        </p>
      </aside>
    </section>
  );
}

function ConnectionDialog({
  apiBase,
  token,
  loading,
  onSubmit,
  onClose,
}: {
  apiBase: string;
  token: string;
  loading: boolean;
  onSubmit: (e: FormEvent<HTMLFormElement>) => void;
  onClose?: () => void;
}) {
  return (
    <div className="modal-backdrop">
      <section
        className="modal connection-modal"
        role="dialog"
        aria-modal="true"
      >
        <div className="modal-head">
          <div>
            <p className="eyebrow">DATABASE CONNECTION</p>
            <h2>连接内容数据服务</h2>
          </div>
          {onClose && (
            <button className="close-button" onClick={onClose}>
              ×
            </button>
          )}
        </div>
        <p className="form-intro">
          管理后台通过独立数据服务读写现有 MySQL。令牌仅保存在当前浏览器。
        </p>
        <form className="editor-form" onSubmit={onSubmit}>
          <Field label="数据服务地址">
            <input
              name="apiBase"
              defaultValue={apiBase}
              placeholder="https://admin-api.example.com/api/admin"
              required
            />
          </Field>
          <Field label="管理令牌">
            <input name="token" type="password" defaultValue={token} required />
          </Field>
          <button className="primary-button full" disabled={loading}>
            {loading ? "正在验证…" : "连接并同步内容"}
          </button>
        </form>
      </section>
    </div>
  );
}

function EditorDialog({
  editor,
  cities,
  routes,
  media,
  request,
  onClose,
  onSaved,
  setNotice,
}: {
  editor: { kind: Kind; item?: Data };
  cities: City[];
  routes: Route[];
  media: Media[];
  request: <T>(p: string, i?: RequestInit) => Promise<T>;
  onClose: () => void;
  onSaved: () => void;
  setNotice: (x: string) => void;
}) {
  const [saving, setSaving] = useState(false);
  const item = editor.item || {};
  const editing = Boolean(editor.item);
  const title = `${editing ? "编辑" : "新建"}${editor.kind === "city" ? "城市" : editor.kind === "route" ? "景点" : "内容节点"}`;
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    const form = new FormData(event.currentTarget);
    const payload: Data = {};
    for (const [key, value] of form.entries()) payload[key] = value;
    if (editor.kind === "city") {
      payload.latitude = Number(payload.latitude);
      payload.longitude = Number(payload.longitude);
    }
    if (editor.kind === "route") {
      payload.slug = payload.slug || str(item.slug) || `scenic-${Date.now().toString(36)}`;
      payload.subtitle = payload.subtitle || str(item.subtitle) || String(payload.title || "");
      payload.difficulty = payload.difficulty || str(item.difficulty) || "轻松";
      payload.theme = payload.theme || str(item.theme) || "城市漫游";
      payload.duration_minutes = Number(payload.duration_minutes);
      payload.distance_km = Number(payload.distance_km);
      payload.is_featured = Boolean(item.is_featured);
      payload.content_status = str(item.content_status) || "draft";
      payload.published_at = item.published_at || null;
    }
    if (editor.kind === "stop") {
      payload.position = Number(payload.position);
      payload.latitude = Number(payload.latitude);
      payload.longitude = Number(payload.longitude);
      payload.arrival_radius_m = Number(payload.arrival_radius_m);
      payload.audio_url = payload.audio_url || null;
      payload.kicker = payload.kicker || str(item.kicker) || String(payload.title || "");
      payload.story_title = payload.story_title || str(item.story_title) || String(payload.title || "");
      payload.insight = payload.insight || str(item.insight) || String(payload.story_body || "");
      payload.image = payload.image || str(item.image) || routes.find((route) => route.id === payload.route_id)?.hero_image || "";
      payload.experience_tags = parseTagText(
        String(payload.experience_tags || ""),
      );
    }
    const endpoint =
      editor.kind === "city"
        ? "cities"
        : editor.kind === "route"
          ? "routes"
          : "stops";
    try {
      await request(`/${endpoint}${editing ? `/${item.id}` : ""}`, {
        method: editing ? "PUT" : "POST",
        body: JSON.stringify(payload),
      });
      onSaved();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="modal-backdrop">
      <section className="modal editor-modal" role="dialog" aria-modal="true">
        <div className="modal-head">
          <div>
            <p className="eyebrow">CONTENT EDITOR</p>
            <h2>{title}</h2>
          </div>
          <button className="close-button" onClick={onClose}>
            ×
          </button>
        </div>
        <form className="editor-form" onSubmit={submit}>
          {editor.kind === "city" && <CityFields item={item} media={media} />}
          {editor.kind === "route" && (
            <RouteFields item={item} cities={cities} media={media} />
          )}
          {editor.kind === "stop" && (
            <StopFields item={item} routes={routes} />
          )}
          <div className="modal-actions">
            <button type="button" className="ghost-button" onClick={onClose}>
              取消
            </button>
            <button className="primary-button" disabled={saving}>
              {saving ? "保存中…" : "保存内容"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

function CityFields({ item, media }: { item: Data; media: Media[] }) {
  return (
    <>
      <div className="form-grid">
        <Field label="城市名称">
          <input name="name" defaultValue={str(item.name)} required />
        </Field>
        <Field label="英文标识">
          <input
            name="slug"
            defaultValue={str(item.slug)}
            placeholder="shanghai"
            required
          />
        </Field>
      </div>
      <Field label="城市副标题">
        <input name="subtitle" defaultValue={str(item.subtitle)} required />
      </Field>
      <MediaField
        name="hero_image"
        label="城市封面路径"
        value={str(item.hero_image)}
        media={media}
      />
      <div className="form-grid">
        <Field label="纬度">
          <input
            name="latitude"
            type="number"
            step="any"
            defaultValue={num(item.latitude, 31.2304)}
            required
          />
        </Field>
        <Field label="经度">
          <input
            name="longitude"
            type="number"
            step="any"
            defaultValue={num(item.longitude, 121.4737)}
            required
          />
        </Field>
      </div>
    </>
  );
}
function RouteFields({
  item,
  cities,
  media,
}: {
  item: Data;
  cities: City[];
  media: Media[];
}) {
  return (
    <>
      <Field label="所属城市">
        <select name="city_id" defaultValue={str(item.city_id)} required>
          <option value="">请选择</option>
          {cities.map((x) => <option value={x.id} key={x.id}>{x.name}</option>)}
        </select>
      </Field>
      <Field label="景点名称">
        <input name="title" defaultValue={str(item.title)} required />
      </Field>
      <Field label="景点介绍">
        <textarea
          name="description"
          defaultValue={str(item.description)}
          rows={4}
          required
        />
      </Field>
      <div className="form-grid">
        <Field label="时长（分钟）">
          <input
            name="duration_minutes"
            type="number"
            min="1"
            defaultValue={num(item.duration_minutes, 90)}
            required
          />
        </Field>
        <Field label="距离（公里）">
          <input
            name="distance_km"
            type="number"
            min="0.1"
            step="0.1"
            defaultValue={num(item.distance_km, 2.5)}
            required
          />
        </Field>
      </div>
      <MediaField
        name="hero_image"
        label="景点封面"
        value={str(item.hero_image)}
        media={media}
      />
    </>
  );
}
function StopFields({
  item,
  routes,
}: {
  item: Data;
  routes: Route[];
}) {
  return (
    <>
      <div className="form-grid">
        <Field label="所属景点">
          <select name="route_id" defaultValue={str(item.route_id)} required>
            <option value="">请选择</option>
            {routes.map((x) => (
              <option value={x.id} key={x.id}>
                {x.city_name} · {x.title}
              </option>
            ))}
          </select>
        </Field>
        <Field label="站点顺序">
          <input
            name="position"
            type="number"
            min="1"
            defaultValue={num(item.position, 1)}
            required
          />
        </Field>
      </div>
      <Field label="节点名称"><input name="title" defaultValue={str(item.title)} required /></Field>
      <Field label="地址">
        <input name="address" defaultValue={str(item.address)} required />
      </Field>
      <div className="form-grid three">
        <Field label="纬度">
          <input
            name="latitude"
            type="number"
            step="any"
            defaultValue={num(item.latitude, 31.2304)}
            required
          />
        </Field>
        <Field label="经度">
          <input
            name="longitude"
            type="number"
            step="any"
            defaultValue={num(item.longitude, 121.4737)}
            required
          />
        </Field>
        <Field label="到达半径（米）">
          <input
            name="arrival_radius_m"
            type="number"
            min="1"
            defaultValue={num(item.arrival_radius_m, 80)}
            required
          />
        </Field>
      </div>
      <Field label="故事文案">
        <textarea
          name="story_body"
          defaultValue={str(item.story_body)}
          rows={7}
          required
        />
      </Field>
      <TagEditor
        name="experience_tags"
        tags={stringList(item.experience_tags)}
      />
    </>
  );
}
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function ChallengeFields({ item, stops }: { item: Data; stops: Stop[] }) {
  const options = Array.isArray(item.options) ? item.options.join("\n") : "";
  return (
    <>
      <Field label="所属站点">
        <select name="stop_id" defaultValue={str(item.stop_id)} required>
          <option value="">请选择</option>
          {stops.map((x) => (
            <option value={x.id} key={x.id}>
              {x.route_title} · {x.position}. {x.title}
            </option>
          ))}
        </select>
      </Field>
      <Field label="问题">
        <textarea
          name="prompt"
          defaultValue={str(item.prompt)}
          rows={3}
          required
        />
      </Field>
      <Field label="提示">
        <textarea name="hint" defaultValue={str(item.hint)} rows={2} required />
      </Field>
      <Field label="选项（每行一个）">
        <textarea
          name="options"
          defaultValue={options}
          rows={5}
          placeholder={"选项 A\n选项 B\n选项 C"}
          required
        />
      </Field>
      <Field label="正确答案序号（第一个选项为 0）">
        <input
          name="correct_option"
          type="number"
          min="0"
          defaultValue={num(item.correct_option, 0)}
          required
        />
      </Field>
      <Field label="答案解析">
        <textarea
          name="explanation"
          defaultValue={str(item.explanation)}
          rows={3}
          required
        />
      </Field>
    </>
  );
}

function ResourcePanel({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="panel resource-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h2>{title}</h2>
        </div>
      </div>
      {children}
    </section>
  );
}
function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

function parseTagText(value: string): string[] {
  return Array.from(
    new Set(
      value
        .split(/[\n,，]/)
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  );
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function parseFootprintSummaryOptions(
  value: string,
): Array<{ id: string; text: string }> {
  return value
    .split("\n")
    .map((line) => {
      const separator = line.indexOf("|");
      return separator < 0
        ? { id: "", text: line.trim() }
        : {
            id: line.slice(0, separator).trim(),
            text: line.slice(separator + 1).trim(),
          };
    })
    .filter((item) => item.id || item.text);
}

function formatFootprintSummaryOptions(value: unknown): string {
  return Array.isArray(value)
    ? value
        .filter((item): item is Data => Boolean(item) && typeof item === "object")
        .map((item) => `${str(item.id)} | ${str(item.text)}`)
        .join("\n")
    : "";
}

function TagEditor({
  tags,
  name,
  onChange,
}: {
  tags: string[];
  name?: string;
  onChange?: (tags: string[]) => void;
}) {
  const [text, setText] = useState(tags.join("，"));
  const normalized = parseTagText(text);
  const helpId = useId();
  const validation =
    normalized.length > 8
      ? "体验标签最多填写 8 个"
      : normalized.find((tag) => tag.length > 24)
        ? "每个体验标签最多 24 个字"
        : "";
  return (
    <Field label="体验标签">
      <textarea
        name={name}
        rows={2}
        value={text}
        placeholder="安静，适合一个人，老建筑"
        aria-describedby={helpId}
        aria-invalid={Boolean(validation)}
        onChange={(event) => {
          setText(event.target.value);
          onChange?.(parseTagText(event.target.value));
        }}
      />
      <small id={helpId}>
        逗号或换行分隔，最多 8 个，每个最多 24 个字；示例仅供参考，可填写新标签。
      </small>
      {validation && <small role="alert">{validation}</small>}
      {normalized.length > 0 && (
        <span className="tag-preview" aria-label="规范化标签预览">
          {normalized.map((tag) => (
            <em className="tag" key={tag}>
              {tag}
            </em>
          ))}
        </span>
      )}
    </Field>
  );
}

function MediaField({
  name,
  label,
  value,
  media,
}: {
  name: string;
  label: string;
  value: string;
  media: Media[];
}) {
  const listId = `media-${name}`;
  return (
    <Field label={label}>
      <input
        name={name}
        defaultValue={value}
        list={listId}
        required={name !== "audio_url"}
      />
      <datalist id={listId}>
        {media.map((x) => (
          <option value={x.storage_path} key={x.key}>
            {x.key}
          </option>
        ))}
      </datalist>
    </Field>
  );
}
function RowActions({
  onEdit,
  onDelete,
}: {
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <span className="row-actions">
      <button onClick={onEdit}>编辑</button>
      <button className="danger-link" onClick={onDelete}>
        删除
      </button>
    </span>
  );
}
function Quick({
  label,
  help,
  icon,
  onClick,
}: {
  label: string;
  help: string;
  icon: string;
  onClick: () => void;
}) {
  return (
    <button className="quick-action" onClick={onClick}>
      <span>{icon}</span>
      <div>
        <strong>{label}</strong>
        <small>{help}</small>
      </div>
      <b>＋</b>
    </button>
  );
}
function StatusTag({ status }: { status: string }) {
  return (
    <em className={`tag ${status === "published" ? "published" : ""}`}>
      {statusLabel(status)}
    </em>
  );
}
function statusLabel(status: string) {
  const label: Record<string, string> = {
    published: "已发布",
    verified: "已审核 · 未发布",
    draft: "草稿",
    in_review: "待审核",
    archived: "已归档",
    demo_unverified: "待审核",
  };
  return label[status] || status;
}
function lifecycleAction(status: string) {
  const label: Record<string, string> = {
    draft: "提交审核",
    in_review: "通过审核",
    verified: "发布上线",
    published: "归档下线",
  };
  return label[status] || "";
}
function TableEmpty({ text }: { text: string }) {
  return <div className="table-empty">{text}</div>;
}
function pad(value: number) {
  return String(value).padStart(2, "0");
}
function str(value: unknown) {
  return value == null ? "" : String(value);
}
function num(value: unknown, fallback: number) {
  return value == null || value === "" ? fallback : Number(value);
}

function narrationErrorMessage(code?: string | null) {
  const messages: Record<string, string> = {
    credentials_unavailable: "MiniMax 凭证未配置",
    credentials_invalid: "MiniMax 凭证无效",
    insufficient_balance: "MiniMax 账户余额不足",
    provider_unavailable: "MiniMax 服务暂时不可用",
    provider_rejected: "MiniMax 拒绝了本次生成请求",
    provider_error: "MiniMax 请求失败",
    invalid_provider_response: "MiniMax 返回了无效音频",
    storage_unavailable: "正式音频存储失败",
    empty_transcript: "旁白文字稿为空",
  };
  return messages[code || ""] || code || "未知错误";
}

function storyStatusLabel(status: string) {
  return (
    {
      draft: "草稿",
      in_review: "审核中",
      approved: "已审核",
      published: "已发布",
      withdrawn: "已撤回",
      archived: "已归档",
    }[status] || status
  );
}

function formatStoryDuration(durationMs: number) {
  const seconds = Math.max(0, Math.round(durationMs / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
