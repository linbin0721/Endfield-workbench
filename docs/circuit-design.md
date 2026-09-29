# 源石电路全链路设计

状态：2026-09-28 设计冻结，按 EW-006 分批实现。

## 目标与边界

- 源石电路与浮空回收使用独立页面：`/circuit` 与 `/balloon`；`/` 是谜题选择首页。
- 两个谜题都支持“截图识别”和“按题号查询”，但各自保留独立题面、目录和结果类型。
- 源石电路使用确定性约束求解；私有截图用于识别校准和回归，不训练端到端解题模型。
- 上传原图不持久化。题号目录只保存规范化题面、图片 SHA-256 和观察次数。
- 功能全部通过验收前，能力接口中的 `circuit` 保持不可用，避免公开半成品入口。

## 已核实的规则与样本事实

- 棋盘包含空闲格、灰色障碍格和已经占用的固定颜色格。
- 每个颜色通道分别拥有逐行、逐列覆盖数量；不同颜色共享同一棋盘，不能重叠。
- 所有库存拼块必须各使用一次，可以旋转 `0°/90°/180°/270°`，不能镜像。
- 行列约束有短条计数和数字两种显示方式；识别层还应接受 `I/II/III/IV/V` 罗马数字，三者统一为整数。
- 当前 `set/train set puzzle/` 有 37 张图，覆盖 18 个实际题面，其中 `V40020` 同时提供数字、短条和完成画面；`set/test set puzzel/` 有 3 张未完成题面。
- 同一可见编号会对应多个不同题面。例如 `V40051`、`V40053` 各有多组输入与完成画面。因此源石电路的编号表示题目组，目录中的不同题面是正常变体，不是数据争议。

## 前端信息架构

```text
/                 谜题选择
/balloon          浮空回收
/circuit          源石电路
```

- 使用 `react-router-dom` 和 `BrowserRouter`。
- Nginx 已使用 `try_files $uri $uri/ /index.html`；Vercel 增加 SPA rewrite，直接刷新子路由不能 404。
- `BalloonPage` 保留现有行为；路由改造不得改变现有接口、识别、目录选择和结果展示。
- `CircuitPage` 内部再选择截图或题号入口。共享图片选择、任务状态和通用错误展示，题面转换与结果绘制保持谜题专用。
- 源石电路截图示例使用项目自制示意图，标出完整棋盘及其行列约束、右侧全部拼块和可选题号，不发布 `set/` 原图。
- 题号查询若只有一个变体可直接求解；有多个变体时展示每个题面的行列约束、障碍和固定格缩略图，由用户选择与游戏画面相符的一项。

## 领域契约

规则版本：`line-count-v1`。

### 题面

```text
CircuitPuzzle
  rule_version
  rows, columns                 2..10
  channels[]                   1..4 个颜色通道
    index                      从 0 连续编号
    row_targets[rows]
    column_targets[columns]
  blocked_cells[]
  fixed_cells[]
    row, column, channel
  pieces[]                     最多 32 个
    channel
    cells[]                    归一化且四连通的局部坐标
```

模型必须拒绝：

- 越界或重复坐标；
- 障碍格与固定格重叠；
- 非连续通道编号；
- 非归一化、断开的拼块；
- 行列目标长度或容量错误；
- 任一通道在某行或某列的固定格数量已经超过对应目标；
- 某通道的行总数、列总数、固定格加库存面积不一致；
- 所有通道在某行或某列的目标总数超过非障碍格容量。

颜色通道是逻辑编号。识别器按色相稳定排序后编号，求解器不依赖具体 RGB。目录指纹还会消除整组通道重编号造成的差异。

### 解答

```text
CircuitPlacement
  piece_index
  row, column                  旋转后包围盒左上角
  rotation                    0 / 90 / 180 / 270

CircuitSolveResult
  outcome                     solved / unsatisfiable / timeout
  rule_version
  solution.placements[]
  limit_reason                time / work，仅 timeout
```

结果不重复保存可由题面和摆放推导出的棋盘。前端按拼块形状、旋转和锚点绘制答案。

## 求解算法

1. 生成每个拼块的四种旋转，平移到局部原点并删除重复方向。
2. 从各通道行列目标中扣除固定颜色格；固定格和障碍格都作为不可覆盖位。
3. 枚举每个拼块的全部合法摆放，记录棋盘 bitmask 及逐行、逐列贡献。
4. 深度优先搜索时选择当前合法候选最少的剩余拼块或相同拼块组（MRV）。
5. 候选按优先满足紧张行列的顺序尝试；正常接口找到第一个解即停止。
6. 每个节点执行以下安全剪枝：
   - 占用冲突和剩余量不得为负；
   - 每个剩余拼块仍有合法候选；
   - 每通道、每行列的剩余量位于剩余候选可贡献的上下界之间；
   - 非障碍空格容量足够；
   - 剩余面积与行列剩余总量相等；
   - 相同通道和形状的拼块使用规范次序，消除交换对称；
   - 缓存已证明失败的 `(占用位图, 剩余拼块组, 行列剩余量)`。
7. 节点数和单调时钟都受现有 `SOLVE_MAX_NODES`、`SOLVE_TIME_LIMIT_SECONDS` 限制。

独立校验器不信任搜索结果，重新旋转每个原始拼块，并验证每块恰好一次、边界、重叠、障碍、固定格以及所有通道的逐行逐列计数。API 只返回通过该校验的解。

## 截图识别

### 输出契约

```text
CircuitRecognitionResult
  outcome                     recognized / incomplete / no_board /
                              already_completed / timeout / invalid_image / failed
  puzzle                      仅完整且一致时提供 CircuitPuzzle
  notation                    bars / digits / roman / mixed，可空
  question_code, question_code_confidence
  catalog                     API 进程完成的目录匹配，可空
  issues[]
```

`recognized` 必须同时带完整 `puzzle`；其余结果不得带题面。不完整或互相矛盾的字段不得猜测成题面。若只识别到题号，可由 API 进程附加该编号已有的目录变体供用户选择。

### 处理步骤

1. 解码并按像素上限缩放，拒绝空文件、超限尺寸和不支持格式。
2. 通过规则网格、重复方格中心和行列标记共同定位棋盘，不使用文件名或单张图固定坐标。
3. 从网格间距推导行列数，分类空闲格、灰色障碍格和固定颜色格。
4. 在棋盘上方和左侧解析约束：
   - 短条模式使用颜色分割、连通域和等距计数；
   - 数字模式只在合法小整数集合内识别；
   - 罗马数字映射到同一整数；
   - `∅` 或明确的空标记归一化为 0；
   - 多色像素先按 HSV 色相聚类，再以稳定顺序映射为通道。
5. 在右侧库存槽内分割每个拼块，根据内部单元格间距还原二值形状，归一化局部坐标并识别通道。
6. 从棋盘左侧 OCR 题号。接受可选三角形、连字符和空格，当前规范值为 `V` 加五位数字或 `WL` 加四位数字，例如 `V40051`、`WL0020`。
7. 执行领域模型的面积、行列总和和容量检查，并调用有界求解器确认可解。全部通过才产生 `puzzle`；棋盘已定位但题面不完整时返回 `incomplete`。
8. 库存已清空且棋盘已有大面积拼块覆盖时返回 `already_completed`，提示用户重置后截图；完成图仅用于离线验收。

OCR 继续在受超时控制的临时子进程中运行。图片识别与求解共享现有单 API 进程内任务队列，上传限流中间件同时覆盖两个精确识别路径。

## 题号目录

源石电路与气球复用 PostgreSQL 实例，但使用独立表和响应模型：

```text
circuit_catalog_entry
circuit_catalog_candidate
circuit_catalog_observation
```

- 编号规范化后保存为 `V40051`、`WL0020`，不保存装饰三角形。
- 同一 `(code, image_sha256)` 只记录一次。
- `CircuitCatalogEntry` 不设置整体争议状态；每个 `CircuitCatalogCandidate` 自带 `provisional` 或 `verified` 状态。
- 同一 `(code, fingerprint)` 聚合观察次数；两张不同图片确认同一题面后，该候选为 `verified`，否则为 `provisional`。
- 同一编号下出现不同指纹时新增正常变体，不覆盖、不合并，也不标记 `disputed`。
- 指纹包含棋盘、约束、固定格和拼块多重集；拼块方向、拼块顺序和颜色通道整体重编号不影响指纹。
- 只有完整、可解并通过独立结果校验的识别题面可以写入。
- PostgreSQL 不可用时截图识别与求解继续工作，只在结果中提示目录暂不可用。

若同一图片摘要已经记录，而新版识别器对它算出不同指纹，目录保留原观察且报告不一致，不用新结果改写历史。候选返回顺序固定为已确认优先、观察数多者优先、首次出现时间优先。

### C1 冻结契约

目录响应固定为 `CircuitCatalogCandidate`、`CircuitCatalogEntry` 和 `CircuitCatalogMatch`：候选包含 `fingerprint/puzzle/status/observations/first_seen/last_seen`；entry 只含 `code/candidates/updated_at`，不设置整体状态；match 包含 `available/code/code_confidence/complete/recorded/duplicate/image_digest_mismatch/matched_fingerprint/matched_status/candidates/issues`。`CircuitRecognitionResult.catalog` 是强类型可空字段，worker 只产生 `null`，API 进程才填充。

`circuit_puzzle_fingerprint` 先用 `CircuitPuzzle` 重新校验，再规范化以下内容：

- 棋盘版本、行列、排序后的障碍格；
- 排序后的固定格及其通道；
- 每个通道的行列目标；
- 拼块多重集。每个拼块的单元格先分别旋转 `0/90/180/270` 度、平移到局部原点并选择字典序最小形状，再与通道绑定并排序。

对 1～4 个通道枚举所有全局重编号，把目标、固定格和拼块通道一起映射；对每种映射生成键稳定、无空白的 JSON，选择字典序最小的有效载荷后计算 SHA-256。因此只忽略全局通道命名，不会把独立交换局部通道、镜像形状或不同目标误合并。

三张表只执行 `CREATE TABLE/INDEX IF NOT EXISTS`。`circuit_catalog_entry` 保存 code 和时间；candidate 以 `(code,fingerprint)` 唯一，保存首个规范有效题面、观察数和时间；observation 以 `(code,image_sha256)` 唯一，保存首次关联指纹。写入事务先建立并锁定 entry 行，再检查摘要：同指纹返回 `duplicate`，不同指纹返回 `digest_mismatch` 且不修改历史；新摘要才插入观察并增加对应候选。候选状态由观察数派生：1 为 `provisional`，至少 2 为 `verified`。查询顺序为 verified 在前、观察数降序、首次时间升序，再用稳定主键打破并列。

`CircuitCatalogService.enrich_recognition` 只在识别结果带规范题号时工作。`recognized` 题面必须在 API 进程重新校验、调用有界求解器并再次调用独立校验器，成功后才能写入；其余 outcome 只查目录。完整截图始终保留并使用本次题面，目录候选只是匹配信息；不完整截图命中一个或多个变体时分别给出明确提示。数据库未配置或不可用时返回 `available=false`，保留原识别结果。服务不吞掉意外编程错误，后续任务 finalize guard 负责保留原结果。

## API

新增具体路由，置于通用占位路由之前：

```text
POST /api/v1/puzzles/circuit/recognize
POST /api/v1/puzzles/circuit/solve
GET  /api/v1/puzzles/circuit/catalog/{code}
```

- 识别和求解均返回现有异步任务视图，通过 `/api/v1/tasks/{id}` 查询。
- 图片限制、队列满、上传繁忙、任务过期和取消语义与气球一致。
- 契约变化后依次导出 `contracts/openapi.json`、运行 `npm run generate:api`、再构建前端。
- 最终验收前才把 `/api/v1/puzzles` 中的 circuit 能力切换为可用并声明 `line-count-v1`。

### C2 冻结契约

应用新增 `CircuitRecognitionTaskView` 和 `CircuitSolveTaskView`，分别把 `TaskView.result` 收窄为 `CircuitRecognitionResult | null` 与 `CircuitSolveResult | null`。`create_app` 可注入独立 `CircuitCatalogService`；未注入时用现有 `CATALOG_DB_*` 配置建立懒连接服务，lifespan 结束时与气球目录服务分别关闭。

三个具体路由必须写在通用占位之前：

- `POST /api/v1/puzzles/circuit/recognize` 只接收一个 `image`，沿用 12 MiB 文件上限、multipart 总量、30 秒接收、并发上传和队列错误语义；计算 SHA-256 后提交 `recognize_circuit_job(data, recognize_limit, solve_limit, solve_nodes)`，并在 API 进程 finalize 中调用电路目录服务。
- `POST /api/v1/puzzles/circuit/solve` 接收 `CircuitPuzzle`，只把服务端求解时间和节点上限传给 `solve_circuit_job`，返回 202 任务；客户端不能覆盖限制。
- `GET /api/v1/puzzles/circuit/catalog/{code}` 使用纯规则规范化题号；非法格式为 422 `INVALID_CODE`，未知为 404 `CATALOG_NOT_FOUND`，目录未配置或不可用为 503 `CATALOG_UNAVAILABLE`，成功返回 `CircuitCatalogEntry` 的全部正常变体。

上传中间件只匹配 `POST` 的 `/api/v1/puzzles/balloon/recognize` 与 `/api/v1/puzzles/circuit/recognize` 两个完整路径，不能影响 GET、后缀路径或通用未知谜题。C2 虽建立可调用的后端契约，但 `PUZZLES["circuit"]` 继续声明 unavailable，直到 D2 页面、类型消费和全链路验收同时完成。导出契约后必须重新生成 TypeScript，禁止手改生成文件。

## 实施批次和验收门槛

### A. 领域核心

- 模型、旋转规范化、求解器、独立校验器。
- 合成用例覆盖单色、多色、障碍、固定格、重复/对称拼块、必须旋转、无解和资源上限。
- 不接 API、数据库、OCR 或前端。

### B. 识别器

- B1a 先实现可单测的数学图像原语：高饱和组件、整数格阵拟合、环形色相聚类、格子特征分类和拼块栅格重建。
- B1b1 提取短条栈及同一棋盘边缘的候选集合，只解决条形组件的尺度、方向、色相、数量和共同基线；不在这一层猜棋盘大小。
- B1b2 将横纵短条候选与方格/角标证据组合成唯一棋盘几何，再把每个颜色的短条映射到行列目标；明确的缺标线归一化为 0，不能唯一补齐时返回不完整。
- B1b3 在已确认几何上分类障碍、固定格和已放置格，分割右侧库存并重建拼块，最后通过领域模型、求解器与独立校验器形成条形模式离线闭环。
- B2 增加数字/罗马数字、题号 OCR、完成画面判定、一次性子进程和端到端结果模型；调用领域模型、求解器和独立校验器形成最终门槛。
- 37 张训练图按 19 张未完成输入和 18 张完成结果建立本机标注清单。19 张输入都要形成可解题面；18 张完成画面都要返回 `already_completed`，不能当作新题面。
- 数字与短条版 `V40020` 必须归一化成相同指纹。3 张测试输入单列结果；其中 `WL0020` 与训练集重叠，不能当作独立泛化证据。

### C. 目录与 API

- C1 新增源石电路目录规则、模型、存储和服务。新表只做 `CREATE TABLE/INDEX IF NOT EXISTS`，不修改或复用气球表；覆盖指纹规范化、幂等写入、同编号多合法变体、候选二次确认、数据库故障降级和并发写入。
- C2 接入三个具体路由和两类任务响应；上传限流同时精确覆盖两个识别路径，路由顺序不能落入通用 501 占位。导出 OpenAPI 并生成前端类型。
- 目录服务在 API 进程再次验证模型、求解结果和独立校验后才写库。完整截图始终优先求解本次识别题面；仅当截图没有完整题面时，才让用户从目录变体中选择。

### D. 路由与页面

- D1 引入 React Router，完成首页、`/balloon`、`/circuit`、导航和深链刷新；先原样搬迁气球页面并做无回归验证。
- D2 加入源石电路双入口、候选缩略图、示意截图和答案棋盘。结果按通道同时使用颜色与编号/纹理，不能只靠颜色传递信息。
- 桌面与窄屏检查键盘操作、忙状态、切换清理、错误信息和结果可读性。

### E. 发布

- 后端全量 pytest、私有样本回归、前端类型生成与生产构建、Compose 和 Nginx 配置检查。
- 变更数据库前备份目录；构建新 API 镜像，健康后再切换前端版本目录。
- 公网验证两个谜题的截图、题号、任务取消、CORS、HTTPS、HTTP 跳转、数据库重启和 API 重启。
- 记录源石电路识别及求解 P50/P95、空闲资源与 10 路并发行为。

## 模块边界

后端新增模块固定如下，避免把气球规则抽象成不适合电路的通用层：

```text
api/app/puzzles/circuit/
  model.py, solve.py, verify.py       已完成的领域核心
  vision.py                           无 OCR、数据库和 FastAPI 依赖的图像原语
  recognize.py                        识别结果模型与一次性子进程监督器
  recognize_worker.py                 解码、OCR 编排、领域/求解门槛和 stdin/stdout 入口
api/app/catalog/
  circuit_models.py                   电路目录响应模型
  circuit_rules.py                    题号规范化、完整性和规范指纹
  circuit_store.py                    三张独立 PostgreSQL 表
  circuit_service.py                  API 进程内的查询、复核与写入
```

前端将现有气球应用迁到 `BalloonPage`，新增 `HomePage` 与 `CircuitPage`。任务轮询和上传控件可以共享，题面校验、候选摘要、答案绘制和题号格式保持谜题专用。`web/vercel.json` 增加 SPA 回退；VPS Nginx 已有 `try_files ... /index.html`，发布时仍需实际检查三个路径直接刷新。

## 识别算法细化

### 棋盘与约束

1. 统一处理 EXIF 方向；解码前后继续执行 12 MiB、2000 万像素、最长边和工作像素限制。
2. 条形模式先提取高饱和细长组件。横条的长边约为格距的 0.31、短边约为 0.10，纵条旋转 90°；同色、同锚点且内部间隔约为格距 0.15 的组件合并为一个数量栈。空间阈值只使用格距比例。
3. 多个数量栈只有在格距相容并共享靠近棋盘的底边或右边时才组成候选集合。页面标题、库存拼块和底部色条即使颜色相同，也不能凭单个连通域成为棋盘证据。
4. 以横纵候选集合给出的格距和棋盘上/左边邻域为先验，在 2～10 行列中枚举棋盘矩形。候选必须同时得到重复方格、格内纹理或四角标记支持，并惩罚矩形外继续出现同格距单元的情况；第一名与第二名过近时拒绝。
5. 先确定棋盘中心线，再按颜色估计约束显示偏移。单色栈应接近对应行列中心；多色约束允许不同颜色在同一行列中心两侧采用稳定偏移，但同一颜色的偏移必须跨行列一致。这样不能把一行中的两种颜色误当成两行。
6. 每个栈只允许映射到一个 `(通道, 行或列)`。已确认棋盘范围内没有相应颜色栈的线是 0；棋盘范围本身未唯一确定时，不得以 0 补齐。每个通道的行目标和列目标总数必须相等。
7. 数字模式从上方与左侧的高饱和度字形位置建立同一格阵；若两轴推导出的步长不一致超过 12%，或角标/格内纹理不支持该候选，拒绝该候选而不强行缩放。
8. 对每格使用内缩采样区：低饱和暗色为可用空格，高亮低饱和条纹/禁用符号为障碍；接近整格的高饱和区域结合居中锁形和独立方框识别固定颜色格，跨内部格线连续的同色区域表示已有拼块并进入 `already_completed` 判定。
9. 从约束、固定格和库存内部取高饱和像素，以环形色相距离聚类 1～4 个通道。每个组件使用中位色相，簇按稳定色相排序；后续指纹仍消除整体通道重编号。
10. 条形约束直接按线位置和通道统计短条数量。数字约束对每个线/通道的小裁剪分别 OCR，只接受 0 到该线长度的阿拉伯数字、`I`～`X` 罗马数字或明确的 `∅`；无法唯一解析时保留不完整状态。

### B1b 中间契约

- `BarStack` 只保存轴向、行列位置、靠棋盘基线、色相、数量、估计格距及归一化残差，不保存图像或掩膜。
- `BarEnsemble` 保存同一基线上的有序短条栈、稳健格距和集合残差；必须至少覆盖两个不同逻辑行列位置。
- `BoardGeometry` 保存棋盘边界、格距、2～10 的行列数、完整中心线和几何置信差；横纵格距相差超过 12% 即无效。
- `BarTargets` 保存按稳定色相编号的通道及完整整数行列目标。重复映射、越界数量、颜色偏移不稳定或行列总数不相等都返回不完整。
- 每层只接受上一层已确认的不可变结果；诊断只含 Python 标量和元组。原图、裁剪、OpenCV 轮廓和 NumPy 数组不能进入返回对象。

B1b2 的公开接口冻结为：

```text
locate_bar_board(image, ensembles) -> BoardGeometry | None
extract_bar_targets(geometry, ensembles) -> BarTargets | None
```

- `BoardGeometry` 字段为 `left/top/right/bottom/step`、`rows/columns`、完整 `row_centers/column_centers`、`evidence_ratio` 和 `score_margin`。四条边表示单元格外边界，中心线长度必须与行列数一致，所有值都是 Python 标量或 tuple。
- `BarTargets.row_targets[channel][row]` 与 `column_targets[channel][column]` 均采用通道优先布局；`channel_hues` 按 OpenCV 环形色相的稳定中心升序，另保留归一化映射残差 `residual_ratio`。
- 棋盘定位枚举横纵 `BarEnsemble` 配对，只接受格距差不超过 12%、基线位于棋盘上/左外侧、且方格轮廓或角标在矩形内部形成重复二维支持的候选。行列范围固定为 2～10；矩形外继续出现同格距单元、只有单轴支持或前两名不同几何过近时返回 `None`。
- 目标解码只使用与已确认棋盘相邻且格距相容的横纵集合。上方横栈映射列目标，左侧竖栈映射行目标；同一颜色的显示偏移分别在两轴内取稳健中位数，偏移或残差不稳定、一个栈映射多个中心、同通道同一行列重复映射时返回 `None`。
- 只有棋盘几何唯一后，缺少物理栈的 `(通道, 行或列)` 才补为 0。任何条数超过对应轴容量、通道超过 4 个或同通道行列总数不相等都返回 `None`；完成画面因高亮吞并而少计的短条不得在本层猜补。

B1b3 按棋盘、库存、闭环三个顺序子批实现，接口冻结为：

```text
extract_board_cells(image, geometry, channel_hues) -> BoardCellMap | None
extract_inventory(image, geometry, channel_hues) -> InventoryState | None
extract_bar_channel_hues(geometry, ensembles) -> tuple[float, ...] | None
analyze_bar_image(image, *, time_limit_seconds, max_nodes) -> BarImageAnalysis
```

- `BoardCellMap.cells[row][column]` 是完整的 `CellClass` 矩阵，另保存所有格子的最低置信度；尺寸必须与 `BoardGeometry` 一致，任何低置信度或通道歧义都返回 `None`。空间采样只按 `step` 和格内比例计算。
- 真实固定格会接近铺满一格，不能只凭颜色面积把它当作已放置拼块。先建立棋盘区域内的通道掩膜和跨格连通关系：跨越内部格线、覆盖多个格子的同色区域属于已放置拼块；单格区域还必须得到居中的锁形高对比结构和四周独立边框支持才属于固定格。单格彩色区域没有锁形证据时保持不完整，不能猜成固定格。
- 障碍格必须同时得到大面积中性灰覆盖和斜纹或禁用符号结构支持。亮度门槛相对同一棋盘的普通空格稳健统计校准，不能依赖某张截图的绝对曝光；背景光晕只能影响置信度，不能单独生成障碍。
- `InventoryState` 保存已确认的完整槽位数、空槽数、置信度和按槽位行优先排序的 `InventoryPiece`。每个拼块保存 `slot_index/channel/cells/rows/columns/iou` 及槽位中心标量，不保存裁剪或掩膜。
- 库存先在棋盘右侧寻找一至两列重复方形槽位，再在每个槽位内按通道色相生成一个干净的四连通掩膜并调用 `reconstruct_piece`。独立搜索到的彩色组件只能作为槽位内容证据，不能替代完整槽位格阵；面板被裁断、一个槽位有多个候选、颜色歧义或形状重建歧义都返回 `None`。
- 完成图的槽位框仍在，但所有槽位为空。只有“确认到完整空库存、棋盘至少有一个已放置的跨格组件、格子状态无歧义”才能返回 `already_completed`；库存仍有拼块且棋盘已有放置组件视为中途状态，返回 `incomplete`。空库存且棋盘没有放置组件也返回 `incomplete`。
- `extract_bar_channel_hues` 只供完成态编排：选择与已确认棋盘相邻且格距相容的唯一横、纵集合，聚类两轴短条色相，并要求每个通道在两轴均有证据。它可以在完成高亮导致行列总数不守恒时保留通道身份，但不得输出或补猜任何目标值。
- `BarImageAnalysis` 只有 `recognized/incomplete/no_board/already_completed` 四种离线结果，保存可选的 `CircuitPuzzle`、已经独立校验的 `CircuitSolution` 和纯文本 `issues`。只有 `recognized` 可携带题面和解答；其余结果两者都为空。
- `analyze_bar_image` 只编排条形模式：依次执行短条、集合、几何、通道、格子、库存和目标解析。普通未完成图必须没有已放置组件，再构造领域模型并依次通过 `solve_circuit` 与 `validate_solution`；模型拒绝、无解、求解超限或独立校验失败都返回 `incomplete`。完成图允许条形目标因高亮吞并而不完整，但仍必须满足上一条的空库存和已放置证据。数字/罗马数字、题号 OCR、进程监督和公开 API 留在 B2。

B2a 的无 OCR 数字符号接口冻结为：

```text
ConstraintGlyph(
    axis: row / column,
    line_index: int,
    channel: int,
    left/top/right/bottom: float,
    center_x/center_y: float,
    hue: float,
)

SymbolLayout(
    geometry: BoardGeometry,
    channel_hues: tuple[float, ...],
    glyphs: tuple[ConstraintGlyph, ...],
    residual_ratio: float,
)

locate_symbol_board(image) -> SymbolLayout | None
```

- 本层只定位紧凑高饱和数字/罗马字形，不解析字符。图形模式的细长计数条继续走 B1，不得被当成字形。
- 横向字形按共同底边形成列候选，纵向字形按共同右边形成行候选；锚点以 2～10 的整数格距解释。横纵候选必须复用条形棋盘相同的方格拟合、格内二维支持、外圈惩罚、12% 方格距门槛和唯一分数门槛。
- 几何唯一后，只保留紧邻棋盘上方/左侧且能唯一映射到中心线的彩色组件。色相聚类为 1～4 通道，每个通道必须在两轴出现且显示偏移稳定；同一 `(axis, line_index, channel)` 的同色近邻组件合并成一个 `ConstraintGlyph`，以支持两位数字或拆分的罗马组合。
- 缺少字形的已确认行列留给 B2b 归一化为 0。本层不读取低饱和 `∅`，只能用棋盘二维证据向候选尾部延伸，不能凭缺字形猜测尚未定位的棋盘范围。

B2b 的已解码图片与 OCR 接口冻结为：

```text
ConstraintToken(value, notation, confidence)
SymbolTargets(channel_hues, row_targets, column_targets,
              notation, minimum_confidence)
QuestionCodeReading(code, confidence, saw_code_like, ambiguous)

parse_constraint_token(text, confidence, maximum) -> ConstraintToken | None
extract_symbol_targets(image, layout, ocr) -> SymbolTargets | None
normalize_circuit_code(text) -> str | None
read_circuit_question_code(image, geometry, ocr) -> QuestionCodeReading
analyze_decoded_image(image, ocr, *, time_limit_seconds, max_nodes)
    -> DecodedImageAnalysis
```

- `ocr` 是注入的单实例识别器；本批只接收已经解码且完成工作尺寸限制的 BGR 图，不实例化 RapidOCR，不读字节、不处理 EXIF、不启动子进程。B2c 的一次性 worker 负责这些边界并把同一 OCR 实例传入。
- 每个 `ConstraintGlyph` 只裁其合并边界外扩 `0.05 × step` 的区域，裁剪到图片范围后通过一次批量 `text_rec` 读取。置信度至少 `0.90`，并且文本经 Unicode 规范化后必须唯一匹配：十进制 `0..maximum`、规范罗马数字 `I..X` 且值不超过 `maximum`，或明确 `∅/Ø` 空标记；`O`、任意夹杂文字、非规范罗马组合、越界值和结果数不一致均拒绝。返回对象不保存裁剪或像素。
- `row` 字形上限是棋盘列数，`column` 字形上限是棋盘行数。同一键不得重复；布局已确认但没有彩色字形的 `(axis, line, channel)` 归一化为 0。各通道行列总数不一致时返回不完整。观察到的数字与罗马标记分别产生 `digits`、`roman`，两类同时出现为 `mixed`；空标记不单独改变 notation。
- 题号只规范化为 `V` 加五位数字或 `WL` 加四位数字，允许前导三角形、连字符、空格和常见 Unicode 破折号，但不进行字母数字猜改。优先搜索相对已确认棋盘的左侧区域，无几何或区域失败时将最长边缩至不超过 1800 后全图回退。置信度至少 `0.95`；多个不同高置信编号视为歧义并留空。题号失败只增加 issue，不得把完整题面降级。
- `DecodedImageAnalysis` 保存四种离线 outcome、可空 notation、可选题号及置信度、纯文本 issues，并沿用只有 `recognized` 能携带题面和已独立校验解答的不变量。先尝试 B2a 数字符号布局；命中后读取数字/罗马目标，否则走 B1 条形闭环。两种模式必须共用格子、库存、完成态、领域构造、求解限制和独立校验语义；条形结果 notation 为 `bars`。题号可在题面不完整甚至未找到棋盘时单独返回，供后续目录查询。

B2c 的正式识别结果与进程边界冻结为：

```text
CircuitRecognitionResult
  outcome                     recognized / incomplete / no_board /
                              already_completed / timeout /
                              invalid_image / failed
  puzzle                      仅 recognized 提供
  notation                    bars / digits / roman / mixed，可空
  question_code, question_code_confidence
  issues[]

recognize_circuit_job(image_bytes, timeout_seconds,
                      solve_time_limit_seconds, solve_max_nodes) -> dict
```

- `CircuitRecognitionResult` 使用 Pydantic、禁止额外字段并重复校验 B2b 不变量；不返回内部 `solution`，因为它只用于确认题面可解，正式求解仍由后续 circuit solve 路由完成。目录匹配字段等 C1 定义强类型模型后再加入，B2c 不使用无类型占位。
- 父任务进程只监督一次性 `python -m app.puzzles.circuit.recognize_worker`：原始图片经 stdin 传入，stdout 只允许单个 JSON，stderr 丢弃，`shell=False`，并设置 OMP/OpenBLAS/MKL/ORT 单线程环境。超时后必须杀死并等待子进程；非零退出、超过 256 KiB 的 stdout、非法 JSON 或不符合模型的结果统一为 `failed`。
- worker 最多读取 12 MiB 加一个字节，只接受 PNG/JPEG/WebP。先从图片头检查正尺寸和不超过 2000 万像素，再按 EXIF 方向转正并转为 RGB；工作图同时满足最长边不超过 3200 和总像素不超过 400 万，缩小使用高质量重采样且绝不放大，最后转成连续 `uint8` BGR。空文件、损坏文件、不支持格式、超字节/像素或 Pillow/OpenCV 解码错误均为 `invalid_image`。
- worker 设置 OpenCV 单线程，只实例化一个 `RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1)`，将同一实例和配置中的求解时间/节点限额传给 `analyze_decoded_image`。已解码结果映射到正式模型时保留题面、notation、题号和 issues，但丢弃内部解答。未捕获的识别异常必须在进程内收敛为 `failed`，stdout 不输出 traceback 或日志。
- B2c 仍不接 HTTP、任务路由、数据库或前端。C2 使用现有任务池调用 `recognize_circuit_job`，上传限流扩展到 circuit 精确路径，并在 API 进程执行目录复核与写入。

B1b3b 的库存返回结构冻结为：

```text
InventoryPiece(
    slot_index: int,
    channel: int,
    cells: tuple[tuple[int, int], ...],
    rows: int,
    columns: int,
    iou: float,
    center_x: float,
    center_y: float,
)

InventoryState(
    slot_count: int,
    empty_count: int,
    pieces: tuple[InventoryPiece, ...],
    minimum_confidence: float,
)
```

- `slot_index` 从 0 开始，按行优先排列；`pieces` 只保存非空槽，并按 `slot_index` 递增。完整空库存是合法的 `InventoryState`，不是 `None`。
- 槽框外边长约为 `1.57 × step`，横纵中心距约为 `1.72 × step`。实现应在棋盘右侧对这些比例保留缩放容差，以灰度局部高频结构的四边独立支持确认槽框，并选择唯一的一列或两列行优先前缀。彩色内容不能补造缺失槽框；前缀有空洞、后续又出现槽框、最后一行或面板被截图边界裁断、两个不同网格近似同优时返回 `None`。
- 每个槽位只采样中央内容区。候选饱和像素必须唯一归属到一个已知通道；未知颜色、两个通道都有实质内容或两个彼此分离的实质组件均返回 `None`。约 `0.04 × step` 的受限闭运算只用于连接同一拼块的描边与填充，随后保留其凹形外轮廓、裁成紧包围盒并调用 `reconstruct_piece`；不得直接从外接矩形猜形状。
- `minimum_confidence` 是全部槽框结构裕量、空槽内容裕量和非空拼块 IoU 的最小值，限制在 `0..1`。无槽框、槽框不完整、颜色或形状不唯一均返回 `None`，不得输出部分库存。

### 库存拼块

1. 搜索棋盘右侧的库存区域，按两列槽位或独立高饱和连通域分割拼块；排除底部装饰色条、文字和小图标。
2. 对每个拼块组件枚举 1～5 行、1～5 列的候选单元格栅。每格以内缩区域的通道像素占比判定占用，重建出的单元格并集与原组件计算 IoU。
3. 只接受 IoU 达标、四连通、面积和包围盒合法且具有唯一最佳网格的形状；再平移到局部原点。库存顺序按槽位从上到下、从左到右固定，但目录指纹忽略该顺序及初始旋转。

### 完整性门槛

- 条形、数字和罗马数字最终都只产生整数行列目标。
- 棋盘尺寸、全部单元格、每个通道的全部行列目标、全部库存形状和通道均已确定，才能构造 `CircuitPuzzle`。
- 构造后依次通过 Pydantic 领域校验、`solve_circuit` 和 `validate_solution`。无解、达到限额或校验失败都不返回题面；问题原因写入 `issues`。
- 识别诊断只记录坐标、分数、候选数和失败阶段，不包含原图像素；调试裁剪只能写到已忽略的本机目录。

## 提交与启用顺序

1. B1a、B1b1、B1b2、B1b3、B2、C1、C2、D1、D2 各自独立提交并完成对应验收；每批只修改列明范围。
2. `main` 上的新代码不会自动替换当前生产容器和静态目录。D2 验收前，生产仍运行既有 release，能力接口继续显示电路不可用。
3. E 批次先备份 PostgreSQL，再构建并检查新 API 镜像；本机与回环验证通过后更新 API，最后原子切换前端版本目录。
4. 只有 API、前端和公网双流程同时通过时才把生产状态记录为源石电路可用；任一步失败就按既有镜像或前端符号链接回滚，新增表和数据保留。

## 回滚

- 前端以版本目录和 `current` 符号链接原子切换，失败时指回上一个 release。
- API 使用本次部署前镜像或 Git 提交重新构建；新增源石电路表对旧 API 无影响，无需删除。
- 不在回滚中删除目录表或卷。需要恢复目录数据时使用部署前 PostgreSQL dump 在隔离环境确认后再处理。
