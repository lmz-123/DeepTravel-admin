"use client";

import { useState, type FormEvent } from "react";

export type TravelPreparation = {
  enabled: boolean;
  admission: "unknown" | "free" | "reservation" | "ticket";
  channel_name: string;
  purchase_url: string;
  launch_mode: "in_app" | "external";
  source_url: string;
  verified_on: string | null;
  opening_hours: string;
  opening_url: string;
  transport: string;
  transport_url: string;
  notices: string;
  notices_url: string;
  extra_items: { title: string; body: string; url: string }[];
};

const empty: TravelPreparation = {
  enabled: false, admission: "unknown", channel_name: "", purchase_url: "",
  launch_mode: "in_app", source_url: "", verified_on: null, opening_hours: "",
  opening_url: "", transport: "", transport_url: "", notices: "", notices_url: "", extra_items: [],
};

type Props = {
  route: { id: string; title: string; content_status: string; travel_preparation?: TravelPreparation | null };
  request: <T>(path: string, init?: RequestInit) => Promise<T>;
  setNotice: (notice: string) => void;
  onChanged: () => void;
};

export default function TravelPreparationEditor({ route, request, setNotice, onChanged }: Props) {
  const [value, setValue] = useState<TravelPreparation>({ ...empty, ...route.travel_preparation });
  const [busy, setBusy] = useState(false);
  const change = <K extends keyof TravelPreparation>(key: K, next: TravelPreparation[K]) => setValue(v => ({ ...v, [key]: next }));
  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true);
    try {
      await request(`/routes/${route.id}/travel-preparation`, { method: "PUT", body: JSON.stringify(value) });
      setNotice("游玩准备已保存。已发布景点在 App 刷新后更新。"); onChanged();
    } catch (error) { setNotice(error instanceof Error ? error.message : "保存失败，请重试"); }
    finally { setBusy(false); }
  }
  const text = (key: "channel_name" | "purchase_url" | "source_url" | "opening_url" | "transport_url" | "notices_url", label: string, url = false) => (
    <label className="field"><span>{label}</span><input value={value[key]} type={url ? "url" : "text"} maxLength={url ? 2000 : 80} placeholder={url ? "https://…" : undefined} onChange={e => change(key, e.target.value)} /></label>
  );
  return <details className="panel travel-preparation-editor" open>
    <summary><strong>游玩准备 · 购票与预约</strong></summary>
    <p className="form-intro">{route.title}的官方入口、开放时间、交通与须知。空白项不会出现在 App；此处不配置票价或虚构订单。已发布景点保存后即更新准备信息，不改变故事发布状态。</p>
    <form className="editor-form" onSubmit={save}>
      <fieldset disabled={busy} style={{ border: 0, padding: 0, margin: 0, display: "contents" }}>
      <label className="checkbox-field full"><input type="checkbox" checked={value.enabled} onChange={e => change("enabled", e.target.checked)} />在 App 显示游玩准备</label>
      <label className="field"><span>入园方式</span><select aria-label="入园方式" value={value.admission} onChange={e => change("admission", e.target.value as TravelPreparation["admission"])}><option value="unknown">暂未确认</option><option value="free">无需门票</option><option value="reservation">免费预约</option><option value="ticket">需要购票</option></select></label>
      <label className="field"><span>入口打开方式</span><select aria-label="入口打开方式" value={value.launch_mode} onChange={e => change("launch_mode", e.target.value as TravelPreparation["launch_mode"])}><option value="in_app">App 内浏览器（失败时转系统浏览器）</option><option value="external">系统浏览器 / 官方关联 App</option></select></label>
      {text("channel_name", "渠道名称（例如：景区官方购票）")}
      {text("purchase_url", "购票 / 预约网页入口", true)}
      {text("source_url", "确认官方身份的来源网页", true)}
      <label className="field"><span>人工核实日期</span><input type="date" value={value.verified_on || ""} onChange={e => change("verified_on", e.target.value || null)} /></label>
      <p className="form-intro full">启用购票入口必须填写渠道、来源及核实日期。微信小程序仅在官方提供可打开的 HTTPS 链接时配置；不填小程序名称、二维码地址或猜测链接。</p>
      {([
        ["opening_hours", "opening_url", "开放时间"],
        ["transport", "transport_url", "到达与停车"],
        ["notices", "notices_url", "入园须知"],
      ] as const).map(([body, url, label]) => <div className="full" key={body}>
        <label className="field"><span>{label}正文</span><textarea rows={3} maxLength={4000} value={value[body]} onChange={e => change(body, e.target.value)} /></label>
        {text(url, `${label}官方详情链接（可选）`, true)}
      </div>)}
      <div className="full"><h3>其他准备事项</h3><p className="form-intro">可增加预约入口、接驳班车、演出安排、天气提醒等，最多 8 项。</p>
      {value.extra_items.map((item, i) => <div key={i} style={{ borderTop: "1px solid #ddd", padding: "16px 0" }}>
        <label className="field"><span>事项标题</span><input required maxLength={40} value={item.title} onChange={e => change("extra_items", value.extra_items.map((x, j) => j === i ? { ...x, title: e.target.value } : x))} /></label>
        <label className="field"><span>正文</span><textarea maxLength={4000} rows={2} value={item.body} onChange={e => change("extra_items", value.extra_items.map((x, j) => j === i ? { ...x, body: e.target.value } : x))} /></label>
        <label className="field"><span>官方链接（可选）</span><input type="url" maxLength={2000} value={item.url} onChange={e => change("extra_items", value.extra_items.map((x, j) => j === i ? { ...x, url: e.target.value } : x))} /></label>
        <button className="danger-link" type="button" onClick={() => change("extra_items", value.extra_items.filter((_, j) => j !== i))}>移除事项</button>
      </div>)}
      <button type="button" className="ghost-button" disabled={value.extra_items.length >= 8} onClick={() => change("extra_items", [...value.extra_items, { title: "", body: "", url: "" }])}>＋ 添加准备事项</button></div>
      <button className="primary-button full" disabled={busy}>{busy ? "正在保存…" : "保存游玩准备"}</button>
      </fieldset>
    </form>
  </details>;
}
