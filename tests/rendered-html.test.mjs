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
  assert.match(html, /<span>09<\/span>运行日志/);
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
  assert.match(admin, /"scenic", "04", "景点内容"/);
  assert.match(admin, /"catalog", "05", "城市故事"/);
  assert.match(admin, /"logs", "09", "运行日志"/);
  assert.doesNotMatch(admin, /\["stories"[^\]]*"首页听故事"/);
  assert.match(admin, /aria-label="选择景点"/);
  assert.match(admin, /\/media\/hierarchy/);
  assert.match(admin, /pretrip\/audio/);
  assert.match(admin, /\/multi-city-import\/preview/);
  assert.match(admin, /确认写入草稿区/);
  assert.match(admin, /\/fragmented-routes\/import/);
  assert.match(admin, /\/routes\/\$\{routeId\}\/validate/);
  assert.match(admin, /submit-review/);
  assert.match(admin, /verified: \{ endpoint: "publish"/);
  assert.match(admin, /已审核 · 未发布/);
  assert.match(admin, /生成 3 个临时试听版本/);
  assert.match(admin, /选用并保存为正式音频/);
  assert.match(admin, /当前线索已保存正式音频/);
  assert.match(admin, /不会自动上线/);
  assert.match(admin, /credentials_configured/);
  assert.match(admin, /一次生成整条路线/);
  assert.match(admin, /一键生成整条路线正式音频/);
  assert.match(admin, /单节点音频纠错（可选）/);
  assert.match(admin, /routes\/\$\{routeId\}\/narration\/generate/);
  assert.match(admin, /\/narration\/config/);
  assert.match(admin, /音色 Voice ID/);
  assert.match(admin, /语速/);
  assert.match(admin, /音调/);
  assert.match(admin, /\/narration\/profiles/);
  assert.match(admin, /narration\/coverage\?profile_id=/);
  assert.match(admin, /profile_id: profile\?\.id/);
  assert.match(admin, /新建音色/);
  assert.match(admin, /当前文字稿覆盖/);
  assert.match(admin, /发布音色/);
  assert.match(admin, /已发布到客户端/);
  assert.match(admin, /新音频已立即发布生效/);
  assert.match(admin, /不需要重复点击发布/);
  assert.match(admin, /暂不能发布/);
  assert.match(admin, /设为默认/);
  assert.match(admin, /最终因果链/);
  assert.match(admin, /史实来源与主张/);
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
