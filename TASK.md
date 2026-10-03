# 当前任务与交接

下一任务编号：`EW-017`。状态流转为“待开始 → 进行中 → 待验收 → 已验收”；只有 Codex 验收后才算完成。

## 当前委派

无。

## 近期完成

### EW-016：电脑截图入口与移动端导入适配

- 状态：已验收；DSH 实现，Codex 独立审查、验证并发布。
- 目标：浮空回收与源石电路在电脑显示“截取游戏窗口”，手机和平板隐藏该入口并优化相册导入及触控布局。
- 范围：共享 `ImageInput.tsx`、少量设备判断/截图辅助模块及局部样式；必要时同步 `docs/frontend-flow.md`。沿用两条解谜路由和现有预览、裁剪、上传与求解逻辑。
- 限制 / 约束：不新增桌面助手、依赖、后端接口或设备模式开关；不修改 325、识别器、求解器、数据库和生产代理。按钮按设备模式决定，不能用窗口宽度隐藏。选图/截屏只本地预览，仍由用户点击“识别并求解”上传。保持 12 MiB / 2000 万像素限制。
- 必要上下文：Windows/macOS/Linux 默认电脑；Android/iPhone/iPad 默认移动，包含桌面 UA 的触控 iPad；不因 Windows 触屏电脑或缩小窗口变为移动。截图使用点击事件内的 `getDisplayMedia`，提示选择游戏窗口，音频关闭，获得真实视频帧后转 PNG，并立即停止所有 track。
- 验收条件：电脑宽/窄窗口均有截图入口；手机和横竖屏平板的 DOM 均无截图按钮；不支持截图的电脑有禁用入口和选图/粘贴提示。成功、拒绝、无帧、源结束、清除与卸载均释放资源，迟到结果不能覆盖新选图；取消授权保留原预览。选图、拖放、粘贴、裁剪和两种解谜流程无回退，两端无横向溢出。
- 验证要求：类型生成、生产构建、差异检查；独立浏览器验证桌面/窄桌面/iPhone/Android/iPad/桌面 UA iPad/触屏 Windows，真实媒体流帧与错误/竞态清理；发布后 HTTPS、CORS、两条解谜路由及实际 API 冒烟。自动化媒体测试与真实 Windows 游戏窗口验证应明确区分。
- 委派约束：DSH 只修改授权文件并在本任务追加回执（实际改动、验证结果、未完成项/风险）；不提交、不推送、不部署，不更新 STATUS/MEMORY。

#### DSH 回执

- 实际改动（按定向审查三项）：
  - 首轮已完成的 `device.ts` 设备判断、点击任务内 `getDisplayMedia`（window 首选 / 排除自身标签）、10 秒无帧上限、`drawImage` 后立即停 track、选择/裁剪/上传链路均未改动。
  - `screenCapture.ts`：`withTimeout` 增加可选 `AbortSignal`。编码等待在预先 aborted 或期间取消时立即 reject，同时清除 timer 与 abort listener，尽快进入 `finally` 移除离屏 video；`drawImage` 后停止 track 的行为保持不变；迟到的 `toBlob` 结果只会落到已 settle 的 promise，被忽略且不写 UI。
  - `ImageInput.tsx`：文件选择改为真实 `type="button"` 并通过 `fileInput.current?.click()` 打开，hidden file input 设 `tabIndex={-1}` 与 `aria-label`；电脑支持截图时“截取游戏窗口”为 primary、选图/更换为 secondary，不支持截图时选图保持 primary、截图按钮禁用并保持 secondary；移动主按钮文案保持“从相册选择”。
  - 文案与局部样式：badge 统一为“图片仅本地预览”；移动提示简化为“先用设备截屏，再从相册选择图片。”，不再提示拖放或电脑截图；section 增加 `image-input-mobile` / `image-input-desktop`，移动设备（含桌面 UA 宽平板）触控区域 ≥44px、输入 `font-size:16px`，窄桌面（420px）截图按钮仍保留。
- 验证结果：
  - `npm run generate:api` 无差异；`VITE_API_BASE_URL=https://api.linbin.org/endfield npm run build` 通过；根目录 `git diff --check` 通过。
  - 三项定向浏览器自查 44/44 通过：`toBlob` 不回调时点击“取消截屏”立即移除离屏 host，track 已 `ended`，迟到回调不产生预览、错误或异常；选图按钮用 Enter 与 Space 均能打开文件选择并载入图片；iPhone 13、Pixel 7、桌面 UA iPad 1024×768 的文案、badge、触控高度与 16px 输入符合要求，无横向溢出。
  - 首轮 mock 媒体流自查脚本整体通过并已归档到 `deploy/.local-backups/ew016-dsh-checks/`（首轮计数记录不一致，不再单列项数）；那属于首轮实现自查，最终版本验收以 Codex 独立验证为准。
- 未完成项 / 风险 / 待决策事项：真实游戏窗口帧、`displaySurface:"window"` 在选择器中的表现和 Windows 实机仍待独立浏览器验证；本机没有真实手机/平板，iOS 聚焦缩放与触控仅由模拟环境核对；未提交、未推送、未部署，未改动 STATUS/MEMORY。
- 建议写入长期记忆：无。

#### Codex 验收

- 独立检查：代码审查后补充原生 `hidden`，避免辅助技术重复暴露文件输入；修正 `InvalidStateError` 提示，使其涵盖页面焦点等启动条件。类型生成无契约差异、生产构建 69 modules、`git diff --check` 通过；Enter/Space 文件选择与隐藏输入独立检查通过。
- 浏览器检查：本地与公网 Chromium 各验证 9 种设备配置 × 2 路由，包括 375px 窄电脑、触屏 Windows、iPhone、Android 手机/平板、iPad 与桌面 UA iPad，横竖屏无溢出。14 项媒体流/错误/取消/迟到结果/编码清理及原有粘贴、拖放、裁剪检查通过，页面异常与意外上传为 0。
- 公网流程：原生视频流模拟捕获真实私有测试图，`WL-A2014` 和 `V40005` 均完成本地预览、识别与求解；所有 track 在上传前结束，recognize/solve 直接请求 VPS。模拟 iPhone 相册导入也成功。HTTPS、有效证书、HTTP 301、CORS 允许/拒绝、三个工具深链与 API 健康通过，API/数据库健康且重启数为 0。
- 结论：EW-016 已验收并上线。自动化替代了系统来源选择框，不代表真实 Windows 游戏窗口、独占全屏或实机手机/平板已经验证；这些保留为体验核对事项。近期完成保留 EW-007 起最近 10 个任务，EW-006 历史见 Git。
- 提交 / 推送：`5b97992805309d76a06fc85bd7e426333024f421`（`feat: add desktop window capture and mobile image import`）已正常推送 `origin/main`；静态 release 为 `/var/www/endfield-workbench/releases/5b97992`，上一版 `ee4ab11` 保留。API、数据库和共享代理配置保持原值。本次验收记录随后正常推送；验证证据与发布前指针保存在已忽略的 `deploy/.local-backups/ew016-*`。

### EW-015：合并 325 调研目录

- 状态：已验收；Codex 直接执行目录整理。
- 目标：将独立的 325 调研资料归入现有 EndfieldWorkbench 项目目录。
- 范围：把 `/root/project/ember-325.MYsK5E/` 移到 `deploy/.local-backups/ember-325/`，在 `AGENTS.md` 更新整体项目目录及各目录职责。
- 限制 / 约束：完整保留文件；目标存在时不得覆盖；调研原始数据继续被 Git 忽略；保持现有生产发布目录和配置。
- 必要上下文：25 个文件共 36,163,257 字节；三个脚本均通过 `__file__` 定位同目录 JSON，没有旧绝对路径引用。
- 验收条件：全部文件迁入项目且内容一致，旧独立目录不再存在，脚本仍可定位数据。
- 验证要求：迁移前后逐文件 SHA-256 对比、JSON 解析、脚本语法、Git 忽略及差异检查。

#### Codex 验收

- 独立检查：25 个文件迁移前后 SHA-256 完全一致，共 36,163,257 字节；22 个 JSON 可解析，3 个 Python 脚本语法通过；25/25 文件被现有规则忽略，Git 跟踪数为 0。正式导入器需要的 13 张表齐全，哈希与 `web/src/calculator/data.json` 的来源记录全部一致。目录说明中的 37 个路径全部存在，近期验收任务共 10 个，`git diff --check` 通过。
- 结论：已归入项目，旧独立目录不再存在；保留全部调研资料。`/325` 已属于同一前端应用，本次没有业务或运行配置变化。近期任务保留 EW-006 起最近 10 个，EW-005 历史见 Git。
- 提交 / 推送：本次只提交目录说明与验收记录，正常推送 `origin/main`；调研原始文件保留本机归档。

### EW-014：325 挑战计算器

- 状态：已验收；Codex 实现计算核心，用户后续授权 DSH 完成独立 UI 部分。
- 目标：新增独立 `/325` 页面，为所有数据集内可用干员寻找一项或多项面板属性显示 325 的方案，多属性方案优先。
- 范围：可复现的数据导入、属性计算与校验、有限时搜索、浏览器 Worker、结果展示、测试和静态发布。
- 限制 / 约束：等级默认满级且可调整；潜能默认 0，支持指定 0～5 或任意潜能；默认提弗洛斯。搜索同武器类型的武器和任意可穿装备；只计算常驻面板属性，排除战斗触发增益。计算器不占用 OCR 队列，不修改 API、数据库或共享代理。
- 必要上下文：此前余烬 P0 双属性、P2 三属性方案用于回归；公开版本化数据需保留来源。数据、规则、搜索目标和 UI 分离，支持后续扩展。
- 验收条件：覆盖数据内全部干员和合法养成阶段；结果注明武器、基质和每条装备锤炼要求；独立复算全部返回方案；准确区分未找到与穷尽无解；手机和桌面可用，支持取消和复制。
- 验证要求：真实基准方案、属性百分比/套装/潜能/等级/武器兼容性测试，搜索性能检查，契约类型生成、生产构建、浏览器验证，发布后 HTTPS 与现有 API 冒烟检查；提交并正常推送。

#### DSH 回执

- 实际改动：限定 `CalculatorPage.tsx`、`calculator.css`、`App.tsx`、`HomePage.tsx`、`SiteLayout.tsx`；新增路由、输入与 Worker 接线、复制/取消、锤炼展示和首页导航。按定向审查修正了词条数组索引、空装备、技术 ID、基质最低需求和路由延迟加载。
- 验证结果：生产构建与差异检查通过；首轮浏览器验证默认值、真实求解、复制、取消和手机布局；最终源码由 Codex 再做独立浏览器检查。
- 未完成项 / 风险 / 待决策事项：DSH 没有提交、推送、部署或修改算法/数据。公开数据尚未在游戏内实际穿戴核对。

#### Codex 验收

- 独立检查：15 项引擎测试全部通过，含余烬 P0 双属性和 P2 三属性基准；33 个干员的 1～90 级/P0/P5 数据检查通过，另对全部 33 个干员执行求解冒烟并复算所有返回结果，全部得到合法方案。源码语义审查覆盖武器主/副能力百分比、三件套 +50、逐词条锤炼和低等级穿戴限制。
- 前端检查：OpenAPI 类型生成无差异，生产构建 67 modules；独立浏览器在 1440px/375px 检查提弗洛斯默认条件、余烬任意潜能三属性、复制、取消、无横向溢出、零页面异常且计算器零 API 请求。提弗洛斯本轮用时约 7.10 秒，余烬三属性约 7.55 秒。
- 性能边界：浏览器 CPU 4 倍降速模拟在 7.68 秒返回 5 个合法双属性方案、375px 无溢出；该模拟不等于所有真实低内存手机已验证。Node 256MiB JS 堆上限下完整默认搜索成功，进程峰值 RSS 约 380MiB。
- 公网检查：`https://endfield.linbin.org/325` 深链与刷新正常；提弗洛斯默认 0 潜能返回三属性 325（本轮 7.10 秒），余烬任意潜能返回 2 潜能三属性方案（7.57 秒）；所有返回方案独立复算一致，复制/取消/手机布局通过。HTTPS、HTTP 301、生产 Origin CORS、API 健康与 `V40005` 查询/求解通过；API/数据库健康且重启数 0。
- 结论：EW-014 已验收并上线。索引/时间预算有限，不承诺全部多解、全局最优或未找到即无解；游戏内显示仍需核对。历史任务只保留 EW-005 起最近 10 个已验收任务，较早记录可查 Git。
- 提交 / 推送：`ee4ab11`（`feat: add extensible 325 challenge calculator`）已推送 `origin/main`；前端 release 为 `/var/www/endfield-workbench/releases/ee4ab11`，旧 `f1f66ba` 保留。API、数据库和共享代理未变更。浏览器/容量证据保存在已忽略的 `deploy/.local-backups/`。

### EW-013：20 路生产并发容量验证

- 状态：已验收
- 目标：模拟 20 名用户同时访问网页、提交求解与真实源石电路截图，测量生产服务的接受率、延迟、健康状态和资源峰值，并判断是否需要增加 worker 或调整其他容量边界。
- 范围：先验证静态页面与轻量求解，再对公网 API 发起 20 路 `V40005` 原图识别突发请求；只执行可控负载测试和记录，不在基线测试前修改生产配置。
- 限制 / 约束：保持单 Uvicorn worker，因为任务状态在单进程内存中；区分 Uvicorn worker、`MAX_WORKERS` 计算进程、`MAX_UPLOADS` 上传槽和 `MAX_QUEUED` 队列。使用现有 2 CPU / 2 GiB API 限额，持续采样健康、进程树 CPU/RSS，测试后确认容器健康、无重启且无遗留任务。
- 必要上下文：宿主机 16 vCPU / 15 GiB RAM；API 容器限制 2 CPU / 2 GiB，当前 `MAX_WORKERS=2`、`MAX_QUEUED=8`、`MAX_UPLOADS=2`。单张 `V40005` 热态识别任务约 4.3 秒，求解约 0.003 秒。
- 验收条件：得到 20 路静态页面、求解和真实截图识别的可复现报告；明确 HTTP 202/429、终态、p50/p95、总耗时、健康请求、CPU/RSS 峰值；根据数据给出是否扩容及应调整哪一层的结论。
- 验证要求：通过公网 HTTPS 路径执行，报告保存在已忽略的 `deploy/.local-backups/`；测试前后检查 Compose、健康、重启次数、日志和空闲资源；不提交原图或负载报告。

#### Codex 验收

- 独立检查：公网 20 路 `/circuit` 页面全部 HTTP 200，p50/p95 为 `695/822ms`。20 路直接求解全部接受并成功，端到端 p50/p95 为 `717/955ms`；20 路题号查询均为 HTTP 200，随后 20 个求解全部成功，查询 p95 `1.16s`、完整流程 p95 `1.40s`。20 路 `V40005` 原图突发上传仅 2 路 HTTP 202，18 路按设计返回 `429 UPLOAD_BUSY` 和 `Retry-After: 5`；接受任务均正确识别并完成，p50/p95 `7.56/7.65s`。识别负载打满 2 核，cgroup 峰值内存约 `767MiB`，12 次健康检查全部 HTTP 200。
- 独立容量实验：使用同一生产镜像启动隔离的 4 CPU / 3 GiB、4 计算进程、16 排队位置、8 上传槽容器；20 路原图突发请求接受 12 路、拒绝 8 路，接受任务全部成功，端到端 p50/p95 `14.57/19.27s`，cgroup 峰值内存约 `1.68GiB`，CPU quota 出现 123 个 throttled period，无 OOM，38 次健康检查全部 HTTP 200。临时容器已删除。
- 结论：20 人同时浏览、按题号查询或求解时现配置足够；20 人同时上传截图时现配置不足。不得增加 Uvicorn worker；任务状态仍要求单 Uvicorn 进程。单独增加计算 worker 也不能解决 2 个上传槽的拒绝，且现有 2 CPU 已饱和。若要正式承诺 20 路截图突发，需要同时加入前端按 `Retry-After` 自动重试/排队、提高上传槽和队列，并配套增加 CPU、计算进程和内存；4 核实验仍未达到 20/20 且尾延迟接近 20 秒。
- 提交 / 推送：负载脚本和完整 JSON 报告位于已忽略的 `deploy/.local-backups/`，不提交；生产配置、容器和代码均未修改。容量结论记录于 `4929c76`（`docs: record 20-user capacity test`）。

### EW-012：消除源石电路题号整图 OCR 回退

- 状态：已验收
- 目标：把新增 `V40005` 截图的识别任务从约 10 秒降到合理范围，同时保持题面、题号和求解结果正确。
- 范围：只优化源石电路题号 OCR 的裁剪策略及对应测试；不修改棋盘/库存视觉算法、题面模型、求解器、目录规则、契约或前端轮询。
- 限制 / 约束：题号只出现在游戏画面左上区域。每张图最多调用一次 RapidOCR 检测，裁剪固定为工作图左上 `28%` 宽、`22%` 高；不再因相对棋盘裁剪未命中而对整图执行第二次 OCR。继续使用严格题号规范化、0.95 置信度门槛、冲突歧义和低置信提示；题号缺失不能阻断题面识别与求解。
- 必要上下文：生产任务 `ee87e1a…` 从 18:20:59.636 到 18:21:09.499，共 9.86 秒，后续 solve 小于 0.2 秒。`cProfile` 显示 `read_circuit_question_code` 用 4.94 秒并执行两次 OCR；第一次几何裁剪从 `board.top - 2*step` 开始，把 `V40005` 上沿切掉，随后触发整图 OCR。固定左上裁剪在 41 张私有样本中命中 38 张，高于现状记录的 36/40，单次 OCR 最大 2.00 秒；新增图命中 `V40005`。
- 验收条件：题号函数对有/无 geometry 都只调用 OCR 一次，裁剪尺寸精确遵守比例并至少为 1 像素；高置信、重复同码、冲突和低置信语义不变；新增图输出同一 `V40005` 完整题面并可求解；41 张回归仍为 38 个题号命中且题面 outcome 不回退；生产等价完整 worker 重复计时有明显下降，目标中位数不高于 5 秒。
- 验证要求：更新 OCR 单元测试；运行 circuit 定向测试、后端相关回归、41 张私有样本审计、`git diff --check`；使用生产镜像依赖和新增原图重复测量完整 disposable worker。DSH 不提交、不推送、不部署。

#### DSH 回执

- 实际改动：
  - `read_circuit_question_code` 保留原有 `(image, geometry, ocr)` 签名，但不再依赖 geometry；对已校验工作图按整数百分比精确向上取整，只截取左上 `28%` 宽、`22%` 高且至少 `1×1` 像素，并且只调用一次 `_ocr_boxes`。删除相对棋盘裁剪、整图缩放及第二次 OCR 回退，原有严格规范化、`0.95` 门槛、同码去重、冲突歧义和低置信语义保持不变。
  - 删除 `ocr.py` 因整图回退消失而不再使用的 `cv2` 导入和 `QUESTION_FULL_FRAME_MAX_SIDE`；新增明确的题号裁剪百分比常量。
  - 更新题号 OCR 单元测试：有/无 geometry 都核对单次调用和精确裁剪像素；覆盖至少 `1×1`、无整图回退、高置信、重复同码、冲突和低置信路径。
- 验证结果：
  - 容器定向测试 `tests/test_circuit_ocr.py tests/test_circuit_analyze.py tests/test_circuit_recognize.py`：`178 passed in 3.46s`。
  - 容器 circuit 与 API 相关回归 `tests/test_circuit*.py tests/test_api.py`：`626 passed, 10 skipped in 13.22s`；10 项为未提供 `CATALOG_TEST_DSN` 时按既有条件跳过的 PostgreSQL store 测试，本批未改目录或存储。
  - 生产镜像依赖下审计 41 张私有电路样本：23 张 `recognized`（22 bars、1 digits）、18 张 `already_completed`，题号命中 `38/41`；所有输入态题面均可求解并通过 `validate_solution`，既有成对题面相等，`FAILURES []`。完整 worker 耗时 min/mean/p50/p95/max 为 `4.195/4.615/4.585/5.000/5.082s`。
  - 新增原图以完整 disposable worker 连跑 5 次，均为 `recognized / bars / V40005`，完整题面均可求解并通过独立校验；耗时 `4.729/4.211/4.278/4.196/4.396s`，中位数 `4.278s`，低于 `5s` 目标。
  - `git diff --check` 通过；修改文件权限均为 `0644`。
- 未完成项 / 风险 / 待决策事项：固定左上单次 OCR 按冻结取舍仍会有 3/41 张旧样本缺少题号，但这些样本的题面识别和求解不受影响；未提交、未推送、未部署。
- 建议写入长期记忆：无；裁剪比例与单次 OCR 限制已经由代码、测试和当前任务记录固化。

#### Codex 验收

- 独立检查：逐项复核固定裁剪、单次调用与兼容语义；独立运行 178 项 OCR、分析和识别定向测试全部通过。使用生产镜像依赖对新增 `V40005` 原图连续运行 3 次完整 disposable worker，分别耗时 `4.480s`、`4.164s`、`4.221s`，均输出 `recognized / bars / V40005`，并可求解且通过独立校验。
- 结论：EW-012 已验收。固定左上 `28% × 22%` 单次 OCR 消除了裁剪未命中后的整图回退；新增样本完整 worker 中位数约 `4.22s`，相对生产原任务 `9.86s` 明显下降，题号、题面与答案没有回退。
- 提交 / 推送：`f170d1e`（`fix: bound circuit code OCR`）已推送 `origin/main` 并部署到生产 API；旧 `4056d5e` 镜像已保留为 `endfield-workbench-api:rollback-4056d5e-20260929T1830Z`。

### EW-011：修正源石电路第二回退色

- 状态：已验收
- 目标：将不存在于游戏中的土黄色第二滑块色改为真实的荧光绿色。
- 范围：只调整源石电路展示层的第二回退色，并同步示例、旧目录无色板候选和无效色板的稳定回退显示。
- 限制 / 约束：第一种青色保持不变；第二种颜色采用真实样本与生产 `V40020` 已识别出的约 77° 绿色；不改变识别色相、正式色板、题面、求解或目录数据。
- 必要上下文：真实双通道完成画面使用蓝青色与荧光绿色，当前 `FALLBACK_HUES` 的第二色为 34° 橙黄色，导致示例出现游戏中不存在的土黄色滑块。
- 验收条件：示例的 L 形和单格滑块及对应固定格均为荧光绿色，第一种青色不变；库存仍为整体 SVG；生产构建和桌面/移动端显示正常。
- 验证要求：运行 `npm run build`、`git diff --check`，浏览器确认第二色为 `hsl(77 72% 55%)`、不存在 `hsl(34 72% 55%)`，并检查无溢出。Codex 自行实现、验收、提交和发布。

#### Codex 验收

- 独立检查：对照私有真实截图中的蓝青色/荧光绿色双通道完成画面，以及生产 `V40020` 已识别的 77.04° 绿色；确认只修改展示层 `FALLBACK_HUES` 第二项。独立运行生产构建、`git diff --check`、模拟 API 浏览器和公网 Edge 154 检查。
- 结论：EW-011 已验收并发布。公网示例三组库存中第一组保持 `hsl(174 72% 55%)`，第二、三组改为 `hsl(77 72% 55%)`；三个固定格使用相同两色，旧 `hsl(34 72% 55%)` 已不存在。整体 SVG 路径、桌面/移动端布局和控制台状态均正常。
- 提交 / 推送：`f1f66ba`（`fix: use in-game circuit fallback colors`）已推送 `origin/main`；生产静态 release 为 `/var/www/endfield-workbench/releases/f1f66ba`。后端、数据库、契约和 Nginx 均未修改。

### EW-010：重做源石电路截图示例的区域与滑块

- 状态：已验收
- 目标：让自制示例更接近游戏解密前画面，并让库存滑块与解密结果使用同一种整体形状、渐变和轮廓表现。
- 范围：只修改源石电路示例组件、必要的共享滑块展示组件及其样式；截图和题号模式继续共用同一画面。
- 限制 / 约束：删除示例中的上方及左侧约束数字、色标和容器；题号、棋盘、库存分别用与浮空回收示例一致的三色边框和 `3`、`1`、`2` 序号标记，标记不得遮挡内容。库存每个多格滑块必须由单一 SVG 填充路径和连续渐变绘制，只显示整体外轮廓，不得出现逐格边框、间隙或重复渐变；复用解密答案的颜色、填充和边界计算，不另造一套视觉语义。画面内不添加区域名称或说明句，区域含义统一写在画面外。不得修改 API、识别、求解、目录、契约或部署配置。
- 必要上下文：EW-009 的示例仍绘制了约束；右侧库存复用 `CircuitPieceShape` 的 CSS 小格网格，导致多格形状看起来像方块堆砌。用户要求移除约束，恢复类似浮空回收示例的三个编号框，并使滑块观感和 EW-008 的完成棋盘一致。
- 验收条件：stage 内没有约束数字或色标；仅有三个清楚的编号区域，`1` 为完整棋盘、`2` 为全部库存、`3` 为可选题号；每个库存形状恰好一个整体填充 path，使用与答案一致的连续渐变和双层外轮廓；多格直条和 L 形内部无小方块边界或缝隙；固定格、障碍和库存颜色协调；外部文字准确解释三个序号；1440px 与 390px 下内容不重叠、不溢出。
- 验证要求：运行 `npm run build` 与 `git diff --check`；浏览器分别检查截图/题号模式 stage 完全一致、约束节点为 0、编号为 `1/2/3`、库存每组 1 个 fill path 且没有逐格 rect；保存桌面与 390px 截图并目视确认。DSH 不提交、不推送、不部署。

#### DSH 回执

- 实际改动：
  - `CircuitGuideExample` 删除上方/左侧约束数字、色标及容器；stage 只保留题号、完整 4×4 棋盘、障碍/固定格和三组库存形状。题号、棋盘、库存分别使用与浮空回收示例相同的紫/青/橙边框及 `3/1/2` 数字标记，标记位于区域内预留位置，不遮挡内容。
  - 截图模式的 stage 外文字说明 1 号棋盘与 2 号库存必需、3 号题号可选；题号模式在 stage 外解释 1/2/3 含义及只需输入 3 号、无需截图。两个 mode 继续渲染相同 stage，画面内没有区域名称或说明句。
  - 新增示例内聚的 `CircuitGuidePiece` SVG 绘制组件，直接复用 EW-008 的 `circuitPieceFill` 与 `circuitPieceBoundarySegments`。每个库存形状使用一个 compound fill path、独立 `userSpaceOnUse` 整体渐变，以及与 `CircuitResult` 相同的 stop、深色主轮廓和亮色细轮廓；不绘制逐格 rect。固定格与库存均从同一 `GUIDE_COLORS` / `CircuitDisplayColor` 集合取色，障碍和固定格继续沿用完成棋盘的现有图形语义。
- 验证结果：
  - 模拟能力 API 的 Playwright 浏览器检查通过：screenshot/code 两种 mode 的 stage 结构签名与可见文本完全一致；stage 文本为 `3 △-V40020 1 2`，旧上/左约束节点和数值均为 0，棋盘 16 格、障碍 1 个、固定格 3 个、库存 3 组。
  - 三组库存分别为 2 格直条、3 格 L 形和单格；每组恰好 1 个 `path[data-circuit-guide-piece-fill]`、0 个 `rect`、2 个 `fill="none"` 外轮廓 path。渐变均为 `userSpaceOnUse`，bounds 分别为 `(0,0)→(1,2)`、`(0,0)→(2,2)`、`(0,0)→(1,1)`；stop 与轮廓颜色精确匹配回退色板，棋盘固定格使用的颜色集合与库存一致。
  - 1440×900 与 390×844 均无横向溢出、无 console/runtime error；截图保存于已忽略的 `deploy/.local-backups/ew010-screenshot-desktop-1440x900.png` 与 `ew010-code-mobile-390x844.png`。目视确认三色区域清楚且编号不遮挡，直条/L 形内部没有逐格边界、缝隙或重复渐变，固定格、障碍和库存配色协调。测试浏览器缺 CJK 字体导致 stage 外中文呈方框，不影响图形审查。
  - 最终常规 `npm run build` 通过（TypeScript + Vite，61 modules transformed）；`git diff --check` 通过；测试 preview 与浏览器子进程已清理。
- 未完成项 / 风险 / 待决策事项：按范围未读取 `set/`，未修改 API、识别、求解、目录、契约、部署或生产服务，未提交/推送/部署；生产字体和实际页面最终观感留给 Codex 发布前验收。
- 建议写入长期记忆：无；示例库存复用完成棋盘几何/渐变/轮廓语义，以及 1/2/3 区域含义，已记录在 EW-010 冻结任务中。

#### Codex 验收

- 独立检查：逐项复核示例组件、共享几何调用和专用样式；独立运行生产构建、`git diff --check` 与模拟 API 浏览器断言。公网 Edge 154 再次验证两种 mode 的 stage 完全一致，约束节点为 0，三个库存形状各有 1 个整体 fill path、0 个 rect 和 2 个外轮廓 path，并目视检查 1440×900 与 390×844 页面。
- 结论：EW-010 已验收并发布。题号、棋盘、库存分别由紫色 3、青色 1、橙色 2 区域框标出；编号不遮挡内容。直条、L 形与单格库存使用和答案一致的连续渐变及整体外轮廓，多格形状内部没有逐格边界、重复渐变或缝隙。桌面和移动端无横向溢出，console/runtime error 为 0。
- 提交 / 推送：`a6fe91b`（`fix: align circuit guide regions and pieces`）已推送 `origin/main`；生产静态 release 为 `/var/www/endfield-workbench/releases/a6fe91b`。后端、数据库、契约和 Nginx 均未修改。

### EW-009：精简源石电路截图示例

- 状态：已验收
- 目标：把截图与题号流程中的自制示例改成接近游戏解密前画面的简洁构图，去除画面内部的教学说明。
- 范围：只修改 `CircuitGuideExample` 及其专用样式；截图和题号两种模式复用同一张未解题示意画面，差异只体现在画面外的简短说明。
- 限制 / 约束：示意画面内部只保留游戏内容所需的题号、约束数字/色标、棋盘、障碍、固定格和库存形状；删除区域编号、必需/可选标签、颜色名称、说明性框选、高亮和弱化效果。所有“截图要包含什么”和“题号在哪里”等提示必须位于画面外。继续使用自制 HTML/CSS 图形，不引入或仿制游戏素材。
- 必要上下文：当前示例把题号、棋盘和库存拆成三个说明卡片，内部包含 `1 必需`、`2 必需`、`3 可选`、`题号位置`、`青色/橙色`等教学文字，并用高亮/弱化表达模式，视觉过于繁琐且不像原始解密画面。
- 验收条件：画面内部没有说明性中文或编号标签；题号仍显示为实际游戏内容 `△-V40020`，上/左约束、完整 4×4 棋盘和三组库存清楚；截图模式的外部提示明确棋盘/约束/库存必需、题号可选；题号模式的外部提示明确题号在棋盘左侧；桌面和 390px 下简洁、无溢出，后续输入流程顺序不变。
- 验证要求：运行前端生产构建和 `git diff --check`；浏览器分别检查两种模式，断言 stage 内不含说明文案/颜色名称且两种 mode 的 stage 结构与内容一致；保存桌面与 390px 截图供 Codex 审查。DSH 不修改 API、识别、求解、目录或部署，不提交、不推送、不部署。

#### DSH 回执

- 实际改动：
  - `CircuitGuideExample` 的 screenshot/code 两种模式现在复用完全相同的中性未解题 stage；模式只决定 stage 外的标题和简短指导。截图提示明确完整棋盘、上/左约束与全部库存必需、左侧题号可选；题号提示明确题号位于棋盘左侧且无需上传截图。
  - stage 内只保留 `△-V40020`、两组约束数值与非文字色标、4×4 棋盘、1 个障碍格、3 个固定格和三组无文字库存形状。删除区域 1/2/3、必需/可选、题号位置、颜色名称、figcaption 教学话术、highlight/dim 状态及说明卡片样式；约束不再复用会输出颜色名的 `CircuitColorToken`。
  - 专用 CSS 改为单一 game-like 三段构图：题号、带上/左约束的棋盘、无文字库存槽位；窄屏保持题号与棋盘并列、库存置于下一行。图形继续由现有自制 HTML/CSS 组成，没有新增图片素材。
- 验证结果：
  - 模拟能力 API 的 Playwright 浏览器检查通过：两种 mode 的 `.circuit-guide-stage` `innerHTML` 和可见文本完全一致；stage 内题号 1 个、上方色标 2 个、左侧约束组 2 个、棋盘格 16 个、障碍 1 个、固定格 3 个、库存槽位/形状 3 组，且 `CircuitColorToken` 为 0。
  - stage 可见文本精确为题号和约束值，不含 `1/2/3 必需/可选`、题号位置、青色/橙色、完整棋盘、全部拼块等指导文案。截图流程 DOM 顺序仍为示意 → 图片输入 → 识别面板，题号流程仍为示意 → 查询表单；两种外部指导分别命中“题号可选”和“无需上传截图”。
  - 1440×900 与 390×844 均为 `document.scrollWidth <= innerWidth`，无 console/runtime error；截图保存于已忽略的 `deploy/.local-backups/ew009-screenshot-desktop-1440x900.png` 与 `ew009-code-mobile-390x844.png`。目视确认 stage 简洁、棋盘/约束/库存完整，库存槽位无文字且窄屏可读；测试浏览器缺 CJK 字体导致 stage 外中文呈方框，不影响结构和图形审查。
  - 最终常规 `npm run build` 通过（TypeScript + Vite，61 modules transformed）；`git diff --check` 通过；测试 preview 与浏览器子进程已清理。
- 未完成项 / 风险 / 待决策事项：按范围未读取 `set/`，未修改 API、识别、求解、目录、部署或生产服务，未提交/推送/部署；最终生产字体与实际页面观感留给 Codex 发布前验收。
- 建议写入长期记忆：无；示意 stage 只展示真实画面内容、两种模式复用同一 stage 的约束已记录在 EW-009 冻结任务中。

#### Codex 验收

- 独立检查：复核组件与专用样式，确认两种入口复用同一未解题 stage，stage 内只保留题号、约束、棋盘和库存。独立运行 `npm run build`（61 modules）及 `git diff --check`；在公网 Edge 154 中分别检查截图与题号流程，并以 1440×900 和 390×844 目视复核。
- 结论：EW-009 已验收并发布。公网 stage 的两种模式结构与文本完全一致，包含 16 格棋盘、1 个障碍、3 个固定格和 3 组库存；不含区域编号、必需/可选、题号位置、颜色名称等说明文字。外部提示和后续表单顺序正确，桌面与移动端均无横向溢出，也没有 console/runtime error。
- 提交 / 推送：`abc4e8b`（`refactor: simplify circuit screenshot guide`）已推送 `origin/main`；生产静态 release 为 `/var/www/endfield-workbench/releases/abc4e8b`。后端、数据库、契约和 Nginx 均未修改。

### EW-008：源石电路拼块整体填充

- 状态：已验收
- 目标：让答案棋盘中的每个库存形状呈现为一块连续、自然的整体，消除每格重复渐变造成的方块拼接感。
- 范围：只调整源石电路成功答案的 SVG 拼块填充路径与渐变坐标；保留现有外轮廓、颜色来源、障碍、固定格、题面预览和交互流程。
- 限制 / 约束：每个 placement 使用一个填充元素和覆盖该形状整体包围范围的连续渐变；不得恢复内部格线，不得合并相邻的不同 placement；不修改后端、契约、识别、求解、目录或部署配置。
- 必要上下文：当前 `CircuitResult` 为一个 placement 的每个格子分别绘制 `<rect>`，通道渐变默认以各 rect 的 object bounding box 重复，导致明暗在每格重新开始。外轮廓已经由 `circuitPieceBoundarySegments` 正确计算。
- 验收条件：直线、L/T/S 和凹形拼块内部没有格状明暗重复或发丝缝；每个拼块只使用一个整体填充路径；同色相邻的不同拼块仍由各自边界清楚分开；固定格和障碍不变；桌面与窄屏无溢出。
- 验证要求：运行前端生产构建和 `git diff --check`；用模拟题面检查一个多格拼块只有一个填充 path、渐变为 `userSpaceOnUse` 且范围等于该拼块包围盒；完成桌面与 390px 浏览器截图供 Codex 审查。DSH 不读取 `set/`、不提交、不推送、不部署。

#### DSH 回执

- 实际改动：
  - 在 `circuitDisplay.ts` 新增 `circuitPieceFill` 纯函数，为一个 placement 生成单一复合 SVG 填充 path 及整体 `x1/y1/x2/y2` 包围范围；填充与既有 `circuitPieceBoundarySegments` 共用同一个单元校验器，统一拒绝空集合、非整数/负坐标和重复单元，避免两套展示几何校验漂移。
  - `CircuitResult` 先为各 placement 推导填充与外轮廓，再给每个 placement 定义独立的 `gradientUnits="userSpaceOnUse"` 线性渐变，渐变起止覆盖该 placement 的完整包围盒。每个 placement 只绘制一个填充 `path`，不再按单元绘制多个 `rect`；原有深浅两层外轮廓继续按 placement 独立绘制，相邻不同 placement 不合并。
- 验证结果：
  - 已忽略的纯函数脚本覆盖直线、L/T/S、凹形、整体 bounds、path 单元子路径数，以及空集合、负数、非整数和重复单元；fill 与 boundary 对同组非法输入均拒绝，检查通过。
  - 模拟 API 的 Playwright 浏览器全流程通过：合成 4×4 题面共 3 个 placement，每组恰好 1 个 `path[data-circuit-piece-fill]`、0 个逐格 `rect`、2 个独立外轮廓 path；横向双格 placement 的渐变为 `userSpaceOnUse`，范围精确为 `(2,0) → (4,1)`。原有 6 次 solve、2 次活动任务取消、非法答案拒绘、色板来源、气球 smoke、焦点和竞态断言同时通过。
  - 1440×900 与 390×844 均无横向溢出；截图保存在已忽略的 `deploy/.local-backups/ew008-desktop-1440x900.png` 和 `ew008-mobile-390x844.png`。目视确认横向双格和 L 形的明暗在整体形状上连续、没有逐格重复渐变或发丝缝，同色相邻的独立 placement 仍有清楚边界，固定格与障碍未变化。测试浏览器缺 CJK 字体导致文字呈方框，不影响图形审查。
  - 最终常规 `npm run build` 通过（TypeScript + Vite，61 modules transformed）；`git diff --check` 通过；测试 preview 与浏览器子进程已清理。
- 未完成项 / 风险 / 待决策事项：按范围未读取 `set/`、未修改后端/契约/识别/求解/目录/部署，未连接生产或部署；浏览器使用合成题面，生产真实题面的最终视觉仍由 Codex 发布前验收。
- 建议写入长期记忆：无；每个 placement 使用一个 user-space 整体渐变填充、不同 placement 不合并的长期约束已记录在 EW-008 冻结任务中。

#### Codex 验收

- 独立检查：复核共用输入校验、复合填充 path、placement 独立渐变 ID 与 user-space bounds，确认固定格、障碍和两层外轮廓未改变。独立运行纯函数检查、`npm run build`（61 modules）和公网 Edge 154 浏览器；生产 V40020 的 4 个 placement 分别只有 1 个填充 path、0 个逐格 rect、2 个外轮廓 path，7/3/4/4 个单元子路径均落在对应整体渐变范围内。
- 结论：EW-008 已验收并发布。桌面和 390px 实际页面中，多格拼块内部渐变连续且没有逐格重复或发丝缝；同色相邻的不同 placement 仍由各自边界分开，页面无横向溢出。
- 提交 / 推送：`d8dc3bf`（`fix: render circuit pieces as unified shapes`）已推送 `origin/main`；生产静态 release 为 `/var/www/endfield-workbench/releases/d8dc3bf`。后端、数据库、契约和 Nginx 均未修改。

### EW-007：源石电路真实颜色与完成棋盘

- 状态：已验收
- 目标：让源石电路答案直接显示为使用截图真实颜色的完成棋盘，用户不需要理解通道编号、拼块编号、坐标或旋转角度。
- 范围：识别色相展示模型、目录色板持久化和旧数据兼容、OpenAPI/生成类型、前端色板接线、游戏风格答案棋盘、候选预览、回归与生产发布。
- 限制 / 约束：冻结契约见 `docs/circuit-result-design.md`。色板不进入领域题面、求解器、独立校验或指纹；主答案不显示 `C1`/`P1`、坐标清单、旋转角度、行列约束，也不增加相关开关；`set/` 原图及派生物不得提交；两个实现批次依次验收，生产发布由 Codex 在两批完成后执行。
- 必要上下文：视觉识别现已得到按通道排序的 OpenCV hue，但正式响应和目录会丢失它；生产电路目录有一个无色板的 `V40020` legacy candidate，迁移必须保留题面和观察历史并只做安全补色。
- 验收条件：截图和题号两条路径使用正确色板；旧候选有稳定回退；同色相邻拼块仍能看出独立轮廓；固定格、障碍、空格和拼块直观可分；非法答案不绘制；气球无回归；生产 HTTPS、CORS、数据库迁移、重启和实际请求通过。
- 验证要求：批次 A/B 分别完成定向和全量验证；最终运行 40 张私有回归、真实临时 PostgreSQL、OpenAPI/类型生成、生产构建、模拟及公网浏览器、数据库备份与重启检查。

#### 当前批次 A：后端色板、目录与契约

- 目标：一次完成视觉色相到正式识别结果、目录候选、PostgreSQL 和生成契约的后端全链路。
- 范围：新增共享展示模型；扩展 analyze/worker/recognition、目录模型/服务/store/fake/API 测试；幂等迁移候选表；重导 OpenAPI 和生成 TypeScript。不得修改求解器、题面模型或指纹语义、手写前端、Compose/Nginx、生产服务或生产数据库。
- 限制 / 约束：严格按设计文档批次 A。`recognized` 色板必须完整匹配题面通道，其他 outcome 为空；候选色板允许空以兼容旧数据；旧候选只在题面 JSON 完全相等时补色；已有非空色板、digest mismatch 和等价但不同表示均不得改色。
- 验收条件：条形/数字/罗马/混合路径输出标准 0～360° 色相；跨进程 JSON 不丢失；目录新写、重复、二次确认、多变体和旧表迁移正确；生成契约出现强类型色板且可重复。
- 验证要求：新增模型、分析、worker、服务、内存与真实 PostgreSQL 测试；相关 circuit 测试和后端全量；OpenAPI 导出、前端类型生成、前端生产构建与 `git diff --check`。不得读取 `set/`，私有真实颜色由 Codex 验收。

#### DSH 回执

- 实际改动：
  - 新增独立的 `CircuitDisplayColor` 展示模型和通道连续性校验；`DecodedImageAnalysis` / `BarImageAnalysis` 只在完整识别时保留按通道排序的 OpenCV hue，worker 在正式 JSON 边界按 `(hue * 2) % 360` 生成标准角度。`CircuitRecognitionResult` 要求 recognized 色板完整且连续，其他 outcome 只能为空。
  - `CircuitCatalogCandidate`、目录 service、`CircuitObservation`、内存 fake 和 PostgreSQL store 全链路保存 `display_palette`。候选表新增 `jsonb NOT NULL DEFAULT '[]'` 并以 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` 幂等迁移；新候选保存首次色板，已有非空色板不覆盖。legacy 空色板仅在 incoming/stored puzzle JSON 相等时补入，duplicate 也执行同一检查，digest mismatch 和同指纹但 JSON 不同的表示均不补色。
  - 扩展模型、分析、worker、service、内存 fake、HTTP/OpenAPI 和真实 PostgreSQL 回归，覆盖 bool/NaN/范围、重复或错序通道、四种 notation、JSON 往返、新写/重复/二次确认/多变体/digest mismatch、非空色板不可覆盖、精确 JSON 补色、等价不同 JSON 不补色及旧表带历史行迁移。重新导出 `contracts/openapi.json` 并由生成器更新 `web/src/generated/api.ts`；未修改手写前端、题面/求解/校验/指纹、部署或生产环境。
- 验证结果：
  - 展示模型、analyze、worker、目录 service/fake 与 API 定向：`170 passed`，仅 1 个既有 Starlette/httpx 弃用警告。
  - 不映射宿主端口的临时 PostgreSQL 17 上真实 store 定向：`10 passed`；带同一临时 PostgreSQL 的后端全量：`712 passed, 5 skipped`，仅 1 个既有弃用警告。5 个跳过项是仓库既有的本地图片样本缺失用例，不包含 PostgreSQL 测试。临时容器 `ew007-postgres` 和网络 `ew007-test` 均已删除，并确认无残留。
  - OpenAPI 连续导出两次、TypeScript 连续生成两次，哈希稳定：`contracts/openapi.json` 为 `0c721645f48583fe897a30473be1443d1dc897fe577d757eb07432eb120e2dae`，`web/src/generated/api.ts` 为 `28a66bcad64fb4dc55f553c1a722e8170cf57e48bcb19706339eee90e126e656`。生成契约包含 `CircuitDisplayColor` 以及 recognition/candidate 的强类型 `display_palette`。
  - `npm run build` 通过（TypeScript + Vite，60 modules transformed）；`git diff --check` 通过；新增文件和生成契约权限均为 0644。
- 未完成项 / 风险 / 待决策事项：按批次边界未读取私有 `set/`、未连接或迁移生产数据库、未部署；真实截图色相对应和生产 legacy `V40020` 补色留给 Codex 独立验收及两批完成后的发布步骤。后端契约和持久化链路没有已知未决实现项。
- 建议写入长期记忆：无；展示色板不参与领域题面/指纹、非空色板不可覆盖及精确 JSON 才能安全补色均已由冻结设计文档记录。

#### Codex 验收

- 独立检查：逐文件核对 hue 传播、正式响应校验、目录服务、内存 fake、PostgreSQL schema/upsert/duplicate 分支及生成契约，确认色板没有进入题面、求解、校验或指纹。独立重跑定向测试 `170 passed`、真实临时 PostgreSQL store `10 passed`、无数据库后端全量 `698 passed, 19 skipped`；其中跳过项为 14 项未接测试数据库和 5 项本机缺少既有 `samples/private/`。OpenAPI 与生成类型哈希和 DSH 回执一致，前端生产构建通过（60 modules transformed），临时数据库容器与网络无残留。
- 结论：批次 A 已验收。识别色相、目录持久化、旧表迁移、安全补色和契约链路达到冻结设计要求；尚未改变当前生产服务。
- 提交 / 推送：`0953eee`（`feat: preserve circuit display colors`）；与批次 B 委派记录一并推送到 `origin/main`。

#### 当前批次 B：完成棋盘与页面接线

- 目标：一次完成前端色板接线和接近游戏完成状态的答案棋盘，让用户只看颜色、形状与位置即可复现答案。
- 范围：新增集中式色板校验和高对比回退；让截图、题号单变体/多变体及不完整截图候选把自己的色板传到预览和答案；重做 `CircuitResult` 与 `CircuitPuzzlePreview` 的彩色矢量表现；补模拟 API 浏览器和响应式回归。不得修改后端识别、题面、求解、目录规则、生成契约或部署。
- 限制 / 约束：严格按 `docs/circuit-result-design.md` 批次 B。主答案不可见 `C1`/`P1`、拼块序号、坐标、旋转角度、行列约束和相关开关；每个 placement 形成内部连续、只有外轮廓的色块，不同 placement 即使同色相邻也必须保留边界；固定格用同色及非文字图形标记；障碍、空格、固定格和拼块可区分；任何缺失或无效色板整组回退，不能部分错配；非法题面或答案仍拒绝绘制。
- 必要上下文：截图完整识别使用 recognition 的 `display_palette`；目录查询、目录候选和不完整截图回退使用 candidate 自己的 `display_palette`；solve API 不接收色板，因此页面在提交求解时必须把题面和色板作为同一来源状态保存，切换模式、候选或任务世代时一起清除。旧生产候选的空色板必须稳定显示固定回退色。
- 验收条件：四通道、旋转、障碍、固定格、同色相邻的两个独立拼块和旧空色板均可直观看懂；答案与候选区无可见技术编号；截图和题号单/多变体都使用正确来源色板；竞态取消不会串色；1440×900 与 390×844 无横向溢出且键盘焦点可用；气球页面无回归。
- 验证要求：新增可独立测试的色板/绘制纯函数；TypeScript 和生产构建；使用模拟 API 的浏览器覆盖截图、题号单/多变体、旧空色板、非法答案和快速切换；检查 DOM 不含禁用文字，并保存桌面/窄屏截图供 Codex 审查。不得读取 `set/`，真实颜色由 Codex 最终回归。

#### DSH 回执

- 实际改动：
  - 新增集中式 `web/src/circuitDisplay.ts`：防御性校验题面与未知色板，只有长度、顺序、连续通道及有限 `[0, 360)` 色相全部有效才采用整组真实色；任一项无效即整组回退四个固定高对比色。保留合法色相精度，避免接近 360° 的值因显示层舍入越界；统一生成 HSL 填充、阴影、亮边和中文颜色名，并以纯函数计算单个库存形状的外露边界。
  - 截图 recognized 使用本次 `display_palette`；题号单变体、多变体及不完整截图目录候选使用各候选自身色板。页面把题面、色板和来源绑定为同一个求解提交状态，沿用既有 generation / abort / cancel 失效路径一起清除；solve 请求体仍只有领域题面。
  - 重做 `CircuitResult` 为 SVG 完成棋盘：先经过既有 `deriveCircuitAnswer` 独立结构校验，再分层绘制底格、障碍、固定格及每个 placement。一个 placement 内无格线且只画外轮廓；不同 placement 即使同色相邻仍各有边界。成功结果仅保留简短说明和棋盘，不显示通道/拼块编号、摆放清单、坐标、旋转、约束、规则版本或相关开关。
  - `CircuitPuzzlePreview`、目录候选及自制示意统一使用真实/回退色、颜色名与纹理；候选仍保留行列数值、棋盘、库存形状、状态和观察次数，不再显示技术通道编号或库存序号。补充窄屏 SVG、色块、纹理、固定格和障碍样式，并删除已无引用的旧通道编号、旧答案棋盘/清单样式及陈旧注释，`.circuit-solution` 只保留一处定义；气球组件及后端、生成契约、部署均未修改。
- 验证结果：
  - 忽略目录中的纯函数脚本通过：覆盖四通道有效色板（含 359.9999° 保持在范围内且命名为红色）、8 组缺失/短项/错序/NaN/Infinity/越界色板的整组回退、颜色命名边界、L/T 形、90°/270° 旋转、同色相邻两个独立形状与合并形状的边界差异，以及重复单元拒绝。
  - `npm run generate:api` 通过，随后 `git diff --exit-code -- contracts/openapi.json web/src/generated/api.ts` 通过，生成契约无差异；`npm run build` 通过（TypeScript + Vite，61 modules transformed）；后端 smoke `test_circuit_presentation.py test_circuit_api.py` 为 **24 passed**，仅 1 个既有 Starlette/httpx 弃用警告；`git diff --check` 通过。
  - Playwright 真实浏览器 + 模拟 API 全流程通过：截图色板 `[12, 204]`、题号单候选 `[132, 24]`、多候选所选变体 `[300, 166]`、legacy 空色板回退 `[174, 34]` 均正确；共检查 6 次 solve、2 次活动任务 DELETE，截图题面未被目录多变体替换，非法答案不绘制，切换/取消无旧答案或串色，答案与候选可见文本不含禁用技术标识，气球双入口 smoke 通过。
  - 1440×900 与 390×844 均为 `document.scrollWidth <= innerWidth`，键盘焦点为 2px solid；截图保存于已忽略的 `deploy/.local-backups/ew007-b-desktop-1440x900.png` 和 `ew007-b-mobile-390x844.png`。目视确认完成棋盘清楚、同色相邻形状边界独立、固定格/障碍/空格可区分；测试浏览器缺 CJK 字体导致截图文字呈方框，不影响布局和图形审查。新增源码权限为 0644，Vite 和本批专用浏览器进程已清理，无临时容器残留。
- 未完成项 / 风险 / 待决策事项：按批次边界未读取 `set/`、未做真实截图颜色核对、未连接生产数据库、未部署；浏览器断言使用模拟 API，真实色相与生产 legacy 候选补色仍由 Codex 在最终私有回归和发布验收中确认。宿主命名空间没有任务指定的 `/opt/microsoft/msedge/msedge`，完整浏览器断言使用 Playwright Chromium 153；另启动的隔离 Edge 154 CDP 复跑在会话中断前未形成可记录的完整结果，相关进程已清理。
- 建议写入长期记忆：无；色板不进入领域题面/求解/指纹、无效色板整组回退和答案只展示完成棋盘均已由冻结设计文档记录。

#### Codex 验收

- 独立检查：逐文件复核色板整组校验、截图/题号/候选来源绑定、竞态清理、SVG 摆放推导和同色拼块边界；独立运行纯展示函数、前端生产构建（61 modules）、后端展示/API smoke（24 passed）及模拟 API 浏览器流程。40 张私有电路原图经正式 worker 边界回归为 21 `recognized/bars`、1 `recognized/digits`、18 `already_completed`，失败 0；22 个完整题面均输出与通道严格对应的色板，输入与对应完成画面的色相差最大 5.45°，题号命中保持既有 36/40。
- 结论：批次 B 与 EW-007 已验收并发布。生产 V40020 实图识别得到 77.04° 色相，legacy 空色板在题面 JSON 精确一致的 duplicate 路径安全补齐；题号查询返回使用该色板的 5×5 完成棋盘。Edge 154 在 1440×900 和 390×844 下确认 4 个库存形状各自有边界、2 个障碍清晰，无技术编号、坐标、旋转或答案约束文字，且没有横向溢出。
- 生产验收：PostgreSQL 迁移前备份 `deploy/backups/circuit-before-ew007-20260929T085002Z.dump` 已通过 `pg_restore -l`；本机/公网健康、TLS、HTTP 301、生产 Origin CORS、非允许 Origin 拒绝、真实截图识别与求解、独立答案复核、10 路并发目录查询、API 重启后色板持久化均通过。API 保持单 Uvicorn worker 和 `127.0.0.1:18000` 回环绑定；空闲快照 API 51.72 MiB、PostgreSQL 28.68 MiB。
- 提交 / 推送：`4056d5e`（`feat: render circuit solutions with recognized colors`，包含已验收的 `0953eee` 后端批次）；已推送 `origin/main`，生产源码与静态 release 为 `4056d5e`。
