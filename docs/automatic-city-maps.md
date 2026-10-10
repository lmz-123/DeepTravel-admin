# 自动城市底图

城市编辑器支持搜索行政城市，选择后填入城市中心、行政区编码和默认标识。无需绘制或上传底图。保存即入队；城市列表自动更新准备状态，失败可重试。地点仍须提供真实坐标，不能以城市中心替代。

服务复用现有公共 OSS 设置，保存 `maps/cities/<adcode>/<sha256>.geojson`。`city_maps` 是与 API 共享数据库中的持久任务/版本表；先部署 DeepTravel API 并执行 Alembic 迁移 `20261011_0019`，再更新 CMS：

```bash
cd "${DEEPTRAVEL_ADMIN_DIR:-/root/DeepTravel-admin}"
git pull --ff-only origin main
docker compose up -d --build admin-api admin-web
```

无需新增环境变量或地图 API 密钥。数据来自 DataV 公共区县边界，城市目录 `server/data/map_cities.json` 来源 `https://geo.datav.aliyun.com/areas_v3/bound/all.json`（2026-10-11）。自动匹配采用准确名称和行政编码，未匹配/未覆盖时不虚构地图。后台周期检查旧城市和新导入城市，失败自动重试；App 保留本地缓存，成功后拉取新的不可变版本。完整部署顺序与验证截图见 DeepTravel 仓库 `docs/automatic-city-maps.md`。

景点 `map_category` 与叙事 theme 独立，可选海边、山野、街巷、建筑、公园、其他；留空兼容旧内容自动识别。真实位置仍由原有地点/故事点坐标配置，城市地图按景点聚合标点。

验证：CMS Python 48 项测试、前端 6 项测试、构建与修改页面 ESLint 通过。完整 tsc 仍有仓库原有的 Cloudflare 类型、扩展名导入、Challenge 类型等错误；对修改前 HEAD 的独立导出执行 tsc 得到相同类别错误，不属于本次地图功能引入。
