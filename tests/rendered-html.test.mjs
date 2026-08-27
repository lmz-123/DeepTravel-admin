import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the DeepTravel admin application", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>简地内容中台<\/title>/i);
  assert.match(html, /景点内容/);
  assert.match(html, /城市故事/);
  assert.match(html, /运行日志/);
  assert.match(html, /<span>07<\/span>运行日志/);
  assert.doesNotMatch(html, /<span>03<\/span>路线|题目管理/);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape|Building your site/i);
});

test("keeps the realtime log surface connected to the independent admin API", async () => {
  const [page, layout, admin, logConsole] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/AdminApp.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/logs/LogConsole.tsx", import.meta.url), "utf8"),
  ]);

  assert.match(page, /<AdminApp \/>/);
  assert.match(layout, /简地内容中台/);
  assert.match(admin, /"scenic", "03", "景点内容"/);
  assert.match(admin, /"catalog", "04", "城市故事"/);
  assert.match(admin, /"logs", "07", "运行日志"/);
  assert.doesNotMatch(admin, /\["routes",\s*"03",\s*"路线"\]/);
  assert.doesNotMatch(admin, /\["challenges"/);
  assert.doesNotMatch(admin, /\["stories"[^\]]*"首页听故事"/);
  assert.match(admin, /aria-label="选择景点"/);
  assert.match(admin, /\/media\/hierarchy/);
  assert.doesNotMatch(admin, /<form[^>]+inline-upload[^>]+pretrip\/audio/);
  assert.match(admin, /\/multi-city-import\/preview/);
  assert.match(admin, /确认写入草稿区/);
  assert.match(admin, /\/fragmented-routes\/import/);
  assert.match(admin, /\/routes\/\$\{routeId\}\/validate/);
  assert.match(admin, /submit-review/);
  assert.match(admin, /verified: \{ endpoint: "publish"/);
  assert.match(admin, /已审核 · 未发布/);
  assert.match(admin, /credentials_configured/);
  assert.match(admin, /景点语音/);
  assert.match(admin, /一次生成出发前和后续全部节点/);
  assert.match(admin, /routes\/\$\{routeId\}\/narration\/generate/);
  assert.match(admin, /\/narration\/config/);
  assert.match(admin, /\/narration\/profiles/);
  assert.match(admin, /narration\/coverage\?profile_id=/);
  assert.match(admin, /一个节点一张卡片/);
  assert.match(admin, /保存这个节点/);
  assert.match(admin, /story_content/);
  assert.match(admin, /city-story-city-card/);
  assert.match(admin, /这里只配置标题和故事内容/);
  assert.match(admin, /生成故事语音/);
  assert.match(admin, /story-catalog\/\$\{saved.id\}\/narration\/generate/);
  assert.match(admin, /保存后使用上方景点语音按钮统一生成/);
  assert.match(admin, /体验标签/);
  assert.match(admin, /规范化标签预览/);
  assert.match(admin, /experience_tags/);
  assert.match(admin, /aria-invalid/);
  assert.match(admin, /体验标签最多填写 8 个/);
  assert.match(admin, /每个体验标签最多 24 个字/);
  assert.doesNotMatch(admin, /recognition_radius_m|discovery_order/);
  assert.match(logConsole, /Authorization.*Bearer/);
  assert.match(logConsole, /text\/event-stream/);
  assert.match(logConsole, /客户端运行日志/);
  assert.match(logConsole, /服务端运行日志/);
  assert.match(logConsole, /无需刷新页面/);
  assert.doesNotMatch(`${page}\n${layout}`, /codex-preview|_sites-preview/);
});
