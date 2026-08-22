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
  assert.match(html, /碎片导览/);
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
  assert.match(admin, /"fragmented", "04", "碎片导览"/);
  assert.match(admin, /"logs", "09", "运行日志"/);
  assert.match(admin, /\/fragmented-routes\/import/);
  assert.match(admin, /\/routes\/\$\{routeId\}\/validate/);
  assert.match(admin, /submit-review/);
  assert.match(admin, /verified: \{ endpoint: "publish"/);
  assert.match(admin, /已审核 · 未发布/);
  assert.match(admin, /生成 3 个试听版本/);
  assert.match(admin, /最终因果链/);
  assert.match(admin, /史实来源与主张/);
  assert.match(logConsole, /Authorization.*Bearer/);
  assert.match(logConsole, /text\/event-stream/);
  assert.match(logConsole, /客户端运行日志/);
  assert.match(logConsole, /服务端运行日志/);
  assert.match(logConsole, /无需刷新页面/);
  assert.doesNotMatch(`${page}\n${layout}`, /codex-preview|_sites-preview/);
});
