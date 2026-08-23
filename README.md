# DeepTravel 独立内容中台

独立管理 DeepTravel 的城市、路线、故事、问题与媒体资源，并提供实时运行日志控制台。管理 Web 与 FastAPI 管理服务分别部署；管理服务连接 DeepTravel 现有 MySQL，不复制业务内容。新增城市和路线通过通用内容包导入、审核和显式发布，不需要修改客户端或旅行 API。

## 运行结构

- `admin-web`：React/vinext 管理界面，默认端口 `3000`。
- `admin-api`：FastAPI 内容与日志管理服务，默认端口 `5100`。
- MySQL：复用 DeepTravel 数据库；管理服务仅额外拥有 `client_runtime_logs` 表。
- 后端日志：管理服务通过配置白名单只读跟随 Docker 容器 stdout/stderr。
- 客户端日志：Flutter 通过独立接收令牌批量提交结构化事件，服务端脱敏后写入 MySQL。
- 媒体与旁白：支持本地存储或阿里云 OSS；以路线为单位一键生成所选 MiniMax 音色的全部节点并保存正式音频，单节点试听与替换仅用于局部纠错。

路线生命周期严格为 `草稿 → 待审核 → 已审核·未发布 → 已发布 → 已归档`。普通编辑不会制造发布时间，旅行端只会看到显式发布且带发布时间的路线。

## 服务器部署

景点体验标签由 DeepTravel 主仓库的 Alembic 迁移
`20260823_0012` 提供（仅新增 `stops.experience_tags_json` 与
`story_fragments.experience_tags_json`）。部署本管理服务前必须先在
`/root/DeepTravel` 执行 `docker compose run --rm api alembic upgrade head`。
管理后台不创建这两个共享列；回滚管理后台代码时保留附加列和已有标签数据。

```bash
git clone git@github.com:lmz-123/DeepTravel-admin.git
cd DeepTravel-admin
cp .env.example .env
docker compose up -d --build
docker compose ps
```

如果仓库已存在：

```bash
cd ~/DeepTravel-admin
git pull origin main
docker compose up -d --build
docker compose ps
```

默认配置按服务器上的 DeepTravel 部署编写。先确认真实容器名：

```bash
docker ps --format '{{.Names}}'
```

然后按 `别名=容器名` 修改 `.env`：

```dotenv
LOG_SOURCES=travel-api=deeptravel-api-1,admin-api=deeptravel-admin-admin-api-1
```

页面只看到 `travel-api`、`admin-api` 等别名，不会收到真实容器名，也不能传入任意容器目标。

## 健康检查与日志验证

```bash
curl -fsS \
  -H 'Authorization: Bearer DeepTravelAdmin2026' \
  http://127.0.0.1:5100/api/admin/health

curl -fsS \
  -H 'Authorization: Bearer DeepTravelAdmin2026' \
  http://127.0.0.1:5100/api/admin/logs/sources
```

提交一条经过接收链路的客户端测试事件：

```bash
curl -fsS -X POST \
  -H 'Content-Type: application/json' \
  -H 'X-Client-Log-Token: DeepTravelClientLogs2026' \
  http://127.0.0.1:5100/api/runtime/client-logs \
  -d '{"events":[{"occurred_at":"2026-08-22T12:00:00+08:00","level":"info","category":"diagnostic","message":"client log pipeline ready","session_id":"manual-check","app_version":"manual","platform":"curl","source":"deployment-check","context":{"check":true}}]}'
```

进入后台“运行日志”即可在同一页面看到“客户端运行日志”和“服务端运行日志”两个持续连接的窗口。两边会自动追加新事件，不需要刷新页面。

## Flutter 客户端上报协议

DeepTravel 主仓库客户端已接入下面协议，会提交框架异常、接口失败、照片上传状态及少量生命周期事件。接收令牌与 `ADMIN_TOKEN` 必须不同，且不授予任何管理权限。

```http
POST /api/runtime/client-logs
X-Client-Log-Token: <CLIENT_LOG_INGEST_TOKEN>
Content-Type: application/json
```

```json
{
  "events": [
    {
      "occurred_at": "2026-08-22T12:00:00+08:00",
      "level": "error",
      "category": "network",
      "message": "GET /cities failed with status 503",
      "session_id": "random-install-session-id",
      "app_version": "1.0.0+12",
      "platform": "android",
      "source": "deeptravel-flutter",
      "context": {
        "operation": "load-cities",
        "connectivity": "wifi"
      }
    }
  ]
}
```

客户端应捕获框架异常、未处理异步异常、API 失败、定位/音频状态失败及少量生命周期事件；不能上传管理令牌、请求头、响应正文、照片、姓名、手机号或精确位置轨迹。离线队列必须有数量和时间上限。

## 安全与保留策略

- 管理日志查询和实时流继续使用 `ADMIN_TOKEN`；客户端只能使用 `CLIENT_LOG_INGEST_TOKEN` 写入。
- 服务端会截断超长字段，并脱敏常见 token、密码、Authorization、Cookie 与数据库连接串。
- 默认客户端日志保留 7 天且最多 20,000 行，写入后执行有上限的清理。
- Docker socket 即使以 `:ro` 挂载仍是高权限能力。管理服务必须保持私有，不应与不可信代码或公开匿名入口共用。
- 如不需要后端容器日志，将 `BACKEND_LOGS_ENABLED=false` 并移除 Docker socket volume。

## 反向代理流式配置

Nginx 代理管理 API 时，应关闭日志流路径的响应缓冲并延长读取超时：

```nginx
location /api/admin/logs/ {
    proxy_pass http://127.0.0.1:5100;
    proxy_http_version 1.1;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 1h;
    add_header X-Accel-Buffering no;
}
```

普通 `/api/admin/` 与 `/api/runtime/` 路径继续代理到 `5100`。生产环境建议使用 HTTPS，避免管理令牌或客户端日志在传输中被窃取。

## 本地验证

```bash
npm ci
npm test
npm run lint

docker compose build admin-api
docker compose run --rm --no-deps admin-api python -m unittest discover -s tests -v
```

MiniMax 真实试听需要显式提供凭证，默认测试不会产生费用：

```bash
cd server
PYTHONPATH=. python ../tools/smoke_minimax_narration.py
```

试听判断标准见 `docs/narration-listening-checklist.md`。OSS 和 MiniMax 密钥只放在服务器 `.env`，不要提交到仓库。

## 回滚

代码回滚后重新执行 `docker compose up -d --build`，并从 Compose 中移除 Docker socket mount。`client_runtime_logs` 是独立的附加表，可以先保留；确认无需审计或导出后再单独删除，回滚过程中不要删除 DeepTravel 的 MySQL volume。
