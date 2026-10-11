# 游玩准备配置

位置：景点内容 → 选择景点 →「游玩准备 · 购票与预约」。

可配置显示开关、入园方式、渠道名称、购票/预约网页、内置/外部浏览器打开方式、官方来源网页与核实日期；开放时间、交通停车、入园须知均可填写正文和链接，另可增加最多 8 项自定义事项（标题、正文、链接）。不需要改 App 或在客户端写死景点。

新景点默认关闭。先人工确认景点/运营方官方入口，记录来源网页和核实日期，再启用。没有可靠入口可以只填写已核实的交通与须知；不填价格、不造链接、不上传个人票据。小程序仅在官方提供可打开的 HTTPS 链接时配置，平台不根据小程序名称自动跳转。

`PUT /api/admin/routes/{id}/travel-preparation` 使用现有管理鉴权，完整替换此配置。已发布景点立即更新准备信息，但不会修改故事发布状态。普通景点编辑和导入不传 `travel_preparation` 时保留原配置；传入时执行同样的校验。公共 API 仅返回已启用配置，未发布景点不对客户端开放。

部署前必须在主项目执行 `20261011_0020` 数据库迁移：

```bash
cd /root/DeepTravel
git fetch origin codex/v5-client-art-magazine
git checkout codex/v5-client-art-magazine
git pull --ff-only origin codex/v5-client-art-magazine
docker compose build api
docker compose run --rm api alembic upgrade head
docker compose up -d api

cd /root/DeepTravel-admin
git pull --ff-only origin main
docker compose up -d --build admin-api admin-web
```

无需新增环境变量。本次未修改生产配置或自动发布景点。

验证：52 项 Python 测试（包含真实鉴权 API/SQLite 配置保存与旧编辑保留）、前端 6 项测试、生产构建、修改页面 ESLint；浏览器通过全部字段保存和刷新回填检查，UI 使用隔离模拟接口。截图见 `docs/verification/travel-preparation/cms-form.png`。

App 第一期购票能力是官方跳转，不获取对方订单；票据由用户自行添加、按账号保存在本机，不上传公共 OSS，不显示虚假的支付/出票成功状态。
