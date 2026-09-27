# 当前任务与交接

下一任务编号：`EW-003`。状态流转为“待开始 → 进行中 → 待验收 → 已验收”；只有 Codex 验收后才算完成。

## 当前委派

暂无。

## 近期完成

### EW-002：截图指引与题号目录

- 状态：已验收
- 目标：增加截图范围示例，并支持按题号查询、截图题号识别和经过校验的题面复用。
- 范围：前端入口与示例图、题号 OCR、持久化目录、查询接口、截图结果与目录记录的比对及冲突处理。
- 限制 / 约束：目录使用仅在 Docker 内网开放的 PostgreSQL；不持久化上传原图；仅保存图片 SHA-256 用于观察去重。题号只接受规范化后的 `WL-A` 加四位数字且 OCR 置信度至少 0.95。新观察不得覆盖既有候选；冲突需同时保留并向用户明确显示。首个完整观察为 `provisional`，同一题面由第二个不同图片摘要再次确认后为 `verified`，出现不同题面则为 `disputed`。OCR 子进程不直接写数据库。
- 必要上下文：新增 13 张完整截图的题号均以 0.994～0.998 置信度识别；旧样本 191530/191752 均为 `WL-A2014` 且题面相同。新增样本中 12 张形成完整题面，202706 仍缺一个升力。公开示例使用已脱敏的 `web/public/balloon-screenshot-guide.png`；原图和其他测试图继续被 Git 忽略。
- 验收条件：第一页可在“截图识别”和“按题号查询”之间选择；示例清楚标出必需的棋盘（含目标总升力）与完整库存，以及可选题号区域。截图流程能识别题号并完成目录新增、匹配、去重和冲突记录；无题号时保持现有识别求解流程；题面不完整但题号命中唯一目录候选时明确提示并可使用目录题面。题号查询可直接求解唯一候选，争议记录必须让用户看到并选择候选。PostgreSQL 有持久卷、健康检查、资源及日志限制且不发布宿主机端口；API 仍为一个 Uvicorn worker。
- 验证要求：新增目录与题号 OCR 单元/接口测试，包括并发或幂等观察、同摘要去重、第二个摘要升级、冲突不覆盖、无效题号、数据库不可用及无题号兼容；导出 OpenAPI 并重新生成前端类型；运行完整 pytest、前端生产构建与 Compose 配置检查。用本地测试集复跑 OCR，并在部署后验证数据库持久化、题号查询、截图完整流程、至少 10 个并发查询、容器重启和公网 HTTPS/CORS。

#### DSH 回执

- 实际改动：
  - 后端新增 `api/app/catalog/`：`rules.py`（题号规范化为 `WL-A` 加四位数字、题面完整性与目标总升力校验、题面指纹）、`models.py`（`CatalogEntry` / `CatalogCandidate` / `CatalogMatch`）、`store.py`（psycopg3 连接池与 entry / candidate / observation 三表，`(code, image_sha256)` 去重、`SELECT … FOR UPDATE` 串行化、状态推导）、`service.py`（识别结果富化与目录查询）。
  - 识别结果新增 `question_code` / `question_code_confidence` / `catalog`；OCR 子进程只在相对棋盘的左栏区域读取题号（外加减采样整图兜底），置信度 ≥0.95 才采用，且不接触数据库。低于阈值时给出提示文案。
  - `TaskManager.submit(..., finalize=…)`：目录写入/查询在 API 进程内、结果返回后执行；钩子抛异常只丢弃富化，不影响识别结果，也不占用任务锁。
  - 新增 `GET /api/v1/puzzles/balloon/catalog/{code}`：422 `INVALID_CODE`、404 `CATALOG_NOT_FOUND`、503 `CATALOG_UNAVAILABLE`；同步处理函数跑在线程池，阻塞的数据库往返不占用单 worker 事件循环。
  - Compose 新增 `db`（postgres:17-alpine）：命名卷 `catalog_data`、`pg_isready` 健康检查、cpus 1 / mem 512m / pids 128 / 日志 10m×3、仅 `expose` 不发布宿主机端口；api 用 `CATALOG_DB_*` 连接并 `depends_on: db (service_started)`，数据库故障不阻塞 API 启动，Uvicorn 仍为 `--workers 1`。
  - 前端：首页新增“截图识别 / 按题号查询”双入口；`GuideExample` 用已脱敏 `web/public/balloon-screenshot-guide.png` 叠加标注棋盘（含目标总升力）、完整库存与可选题号区域；`CatalogCandidates` 展示冲突候选供选择；`CodeQuery` 支持唯一候选直接求解；识别面板显示题号、目录状态、去重/升级/冲突与目录不可用提示。
  - 契约：重新导出 `contracts/openapi.json` 并生成 `web/src/generated/api.ts`；凭据只写入被忽略的 `deploy/.env`，`deploy/.env.example` 增加占位说明。
  - 测试：新增 `tests/test_catalog.py`（31 项）、`tests/test_catalog_store.py`（PostgreSQL 4 项，未设置 `CATALOG_TEST_DSN` 时跳过）、`tests/catalog_fakes.py`；`test_recognition.py` 增加题号阈值单测与公开示例图真实 OCR 复验。
- 验证结果：
  - 后端全量 pytest（容器内、仓库挂载）：无数据库 67 passed / 8 skipped；接真实 PostgreSQL 17 临时实例 71 passed / 5 skipped，跳过项全部是缺失的 `samples/private/` 旧样本。
  - 覆盖同摘要幂等、第二个不同摘要升级 `verified`、不同题面保留双方并置 `disputed`、12 线程并发同图只记一次、无效题号、未知题号、数据库不可用、无题号时 `catalog=None` 且不触碰目录、finalize 异常不影响识别。
  - 真实 PostgreSQL：10 线程并发同摘要只产生 1 条观察；HTTP 上传→任务→API 进程 finalize→PG→题号查询全链路通过。
  - 题号 OCR：公开示例图实测 `WL-A1001` 置信度 0.9985（≥0.95），识别仍为 draft 且 `catalog` 只由 API 进程填充。
  - 容器级联调：生产镜像（已含 psycopg）连临时 PG，目录查询 200；停库后健康检查仍 200、目录 503 `CATALOG_UNAVAILABLE`；重启库后自动恢复 200；10 个并发查询全部 200、数据一致。
  - 前端：`npm run generate:api` 后 `npm run build`（tsc + vite）通过，`dist/` 含示例图；后端 `docker compose config` 与 `-f compose.yaml -f compose.vps.yaml` 均通过，合并配置确认 db 无宿主机端口、有命名卷/健康检查/资源与日志限制。
  - 未提交、未推送、未部署；生产容器未重启（仍为旧镜像 ID 运行）。
  - 复跑方式：本机现有 `endfield-workbench-api-test:latest`（由 api 镜像加 `requirements-dev.txt` 构建）可直接 `docker run --rm -v "$PWD:/repo" -w /repo/api -e CATALOG_TEST_DSN=… endfield-workbench-api-test:latest python -m pytest`；不设 `CATALOG_TEST_DSN` 时 PostgreSQL 用例自动跳过。
- 未完成项 / 风险 / 待决策事项：
  - 按本轮要求未读取被 Git 忽略的 `test set/` 原图，13 张新截图未复跑；题号区域依赖棋盘相对位置，另有降采样整图兜底，仍需部署后用真实样本确认召回率与耗时增量（最坏情况多一次整图 OCR）。
  - 部署后验证（持久卷跨容器重建、公网题号查询与截图全流程、≥10 并发公网表现、容器重启、HTTPS/CORS）未执行，留给 Codex 验收。
  - 只有完整且校验通过的题面才写目录（棋盘无未知格、库存齐全、目标总升力等于库存合计）；不完整观察不落库，因此脱敏示例图本身不会产生目录记录。
  - 目录状态只升不降，出现第二个不同题面后长期为 `disputed`，没有人工裁决/合并接口，用户只能选择候选求解。
  - `deploy/README.md`、`api/README.md` 中“`config --services` 只打印 api”等描述已过时（现在还有 `db`），本轮按要求未改文档。
  - `web/public/balloon-screenshot-guide.png` 仍未被 Git 跟踪，提交时需一并加入；`deploy/.env` 已新增 `CATALOG_DB_*`（随机密码，仅本机，不提交）。
- 建议写入长期记忆：题号目录三条不变量——同一 `(code, image_sha256)` 只记一次、只有完整且校验通过的题面才入库、候选只增不覆盖且状态由候选数与确认数推导（单候选 1 次观察 `provisional`、同候选第二个不同摘要 `verified`、≥2 候选 `disputed`）；目录写入必须留在 API 进程（TaskManager finalize），OCR 子进程只回 JSON；PostgreSQL 只在 Compose 内网、凭据只在被忽略的 `deploy/.env`，数据库不可用时识别与求解必须继续可用；前端依赖 `catalog.issues` 中“唯一完整题面 / 多个不同题面 / 未重复计数 / 已确认”等提示语义，改结构化字段时需同步契约与前端。

#### Codex 验收

- 独立检查：修正被阻挡格的目录规范化、完整截图库存裁剪和标签定位、唯一缺失升力推导、不可解题面入库、查询组件卸载竞态以及重复求解和旧结果残留。随后用真实 PostgreSQL 17 运行后端全量测试，复跑本机全部 19 张截图并检查生产环境上传、目录写入、独立解答校验、10 路并发查询、数据库与 API 分别重启后的持久化恢复、HTTPS、CORS、端口和空闲资源。
- 结论：已验收并发布。后端为 74 passed / 5 skipped；19 张截图均完成生产识别，18 张可求解，15 个完整且可解的带题号题面写入目录，191530 的不可解误识别被目录校验拒绝。公开示例 `WL-A1001` 已实际求解并通过独立校验；15 条目录记录在数据库与 API 重启后均可查询。前端生产构建、OpenAPI 类型生成、Compose 与 Nginx 配置检查均通过。
- 提交 / 推送：`ce0d6eed1319db77e2620a0e41075322be7aa9e0` 已推送到 `origin/main`；API、PostgreSQL 和前端均按该提交发布。

### EW-001：兼容第四行气球库存数量缺失

- 状态：已验收
- 目标：修复四种气球时第四行数量被截图底边裁掉而无法求解的问题。
- 范围：库存识别、严格推导、前端来源提示、测试和相关说明；根目录 `test set/` 作为私有样本忽略。
- 限制 / 约束：不得凭空补值；只有唯一、整数、满足库存与可用格限制且经总升力复核的结果才能采用。
- 必要上下文：两张四行样本基线均为 6×1 / 3×1 / 2×3 / 空，目标 18；另有三张不同分辨率样本用于回归。
- 验收条件：两张四行图可识别并求解，已有可用样本不回退，测试图片不进入 Git。
- 验证要求：完整后端测试、前端生产构建、5 张本地截图复跑、生产环境实际上传与求解。

#### DSH 回执

- 实际改动：新增纯逻辑库存推导；目标置信度至少 0.85、无刚发生的总升力冲突且候选唯一时，才补一个缺失数量或一整行。库存“升力”文字作为补充证据，等级数字不当作升力；前端显示推导来源。
- 验证结果：后端 34 passed / 5 skipped，前端构建通过；两张四行图均推导为 1×3 并求解、独立校验通过；OpenAPI 结构未变化。
- 未完成项 / 风险 / 待决策事项：191530 同时缺两个数量，仍拒绝求解；`samples/private/` 不存在导致 5 项旧样本测试跳过；真实两位数升力文字当前按歧义处理。
- 建议写入长期记忆：保留严格推导条件、冲突后禁止回填，以及后端推导提示与前端展示之间的兼容约定。

#### Codex 验收

- 独立检查：修正失败提示误触发前端推导提示和文字 OCR 值 `0` 两处边界；重跑后端测试、前端构建、5 张样本和公网完整流程。两张四行图均得到 6×1 / 3×1 / 2×3 / 1×3，8 个气球的总升力为 18，行列力矩均为 0。
- 结论：已验收并发布；HTTPS、CORS、容器健康和回环端口检查通过。
- 提交 / 推送：`917fd79a0a0d05702bfb2026d652901fd97e22b4` 已推送到 `origin/main`，API 与前端均按该提交发布。

## 任务模板

### EW-003：任务标题

- 状态：待开始
- 目标：
- 范围：
- 限制 / 约束：
- 必要上下文：
- 验收条件：
- 验证要求：

#### DSH 回执

- 实际改动：
- 验证结果：
- 未完成项 / 风险 / 待决策事项：
- 建议写入长期记忆：无 / 具体内容及原因

#### Codex 验收

- 独立检查：
- 结论：已验收 / 需返工 / 阻塞
- 提交 / 推送：
