# Endfield Workbench 项目说明

本文件只补充本项目特有约定。通用协作、安全和验证规则遵循 Codex 与 DSH 的全局 `AGENTS.md`。

## 技术栈与目录

前端使用 React 19、TypeScript、Vite，生产产物为静态文件；后端使用 FastAPI、OpenCV、RapidOCR，题号目录存储使用 PostgreSQL。

项目根目录为 `/root/project/EndfieldWorkbench/`，主要结构如下：

```text
EndfieldWorkbench/
├── AGENTS.md                   项目说明与约束
├── TASK.md                     任务交接、验收及完整历史
├── STATUS.md                   已核实的当前状态
├── MEMORY.md                   长期决策与兼容背景
├── web/                        前端应用
│   ├── src/
│   │   ├── App.tsx             /:locale 首页及 balloon、circuit、325 子路由；旧地址兼容；工具页按需加载
│   │   ├── shell/              站点框架：顶栏导航、手机菜单、语言与主题切换、加载态与 404
│   │   ├── ui/                 设计系统：tokens、深浅底面、基础层序与通用组件，见 docs/ui-design.md
│   │   ├── tools/              工具清单，导航、首页入口与路由的单一来源
│   │   ├── features/
│   │   │   ├── home/           首页与等高线背景
│   │   │   ├── workbench/      两种解谜共用的导入、裁剪、三步进度、帮助面板与任务轮询
│   │   │   ├── balloon/        浮空回收：题面草稿与编辑、目录候选对比、答案棋盘
│   │   │   ├── circuit/        源石电路：草稿与编辑、目录候选对比、校验后的答案与主题配色
│   │   │   └── calculator/     325 配装台：条件、方案对比、配装与属性来源拆分
│   │   ├── api.ts              API 客户端与契约类型别名
│   │   ├── puzzle.ts           浮空回收题面校验
│   │   ├── circuit.ts          源石电路题面校验、旋转与答案独立推导
│   │   ├── circuitDisplay.ts   电路色板解析与拼块绘制几何
│   │   ├── device.ts          电脑与手机/平板入口判断，独立于窗口宽度
│   │   ├── screenCapture.ts   单帧窗口截图与媒体资源释放
│   │   ├── i18n/               四语资源、语言路由、消息展示兼容与游戏名称来源
│   │   ├── calculator/         版本化数据、领域模型、属性复算与 Worker 搜索
│   │   │   └── media/          325 本地图标、实体链接及来源/哈希记录，独立于数值计算
│   │   └── generated/          从 OpenAPI 生成的 API 类型
│   ├── public/                 静态素材与截图示例
│   └── tests/                  325 计算与搜索、四语资源测试
├── api/                        后端应用
│   ├── app/
│   │   ├── main.py             FastAPI 入口与接口
│   │   ├── tasks.py            单进程内存任务队列
│   │   ├── catalog/            题号目录、PostgreSQL 存储与识别对账
│   │   └── puzzles/
│   │       ├── balloon/        浮空回收识别、求解与独立校验
│   │       └── circuit/        源石电路识别、求解与独立校验
│   ├── tests/                  后端测试
│   ├── bench/                  压测脚本
│   └── export_openapi.py       契约导出入口
├── contracts/openapi.json      后端导出的 OpenAPI 契约
├── tools/import_calculator_data.py  325 公开数据导入入口
├── tools/import_calculator_media.py  325 图标导入与全量离线审计
├── tools/import_calculator_names.py  同版本四语游戏名称导入与离线审计
├── deploy/                     Compose、Caddy 基础与 VPS Nginx 部署配置
│   ├── backups/                本地部署备份，Git 忽略
│   └── .local-backups/         本地验证证据、缓存与调研资料，Git 忽略
│       └── ember-325/           325 原始数据表、试算脚本与核验结果
├── docs/                       产品、架构、界面、规则、识别与压测文档
├── set/                        私有训练/测试样本，Git 忽略
│   ├── test set baloons/       浮空回收回归样本
│   ├── train set puzzle/       源石电路训练样本
│   ├── test set puzzel/        源石电路测试样本
│   └── test set issue/         用户反馈问题的原图回归样本
└── app/                        本机现有空目录；后端源码位于 api/app/
```

- `/325` 与两种解谜工具属于同一前端应用；`ember-325/` 是本地调研归档。正式数据更新使用 `tools/import_calculator_data.py`。
- `docs/tasks.md` 保存早期开发验收历史；`samples/private/` 是旧私有识别样本约定路径，当前 VPS 缺失。
- 样本原图、派生审计图和本地调研缓存不进入 Git；样本目录改名时同步脚本及项目内路径引用。

## 项目约束

- API 任务状态保存在进程内，生产环境必须保持一个 Uvicorn worker，不得横向扩容 API 容器。
- PostgreSQL 只在 Compose 内网提供服务，不发布宿主机端口；上传原图不落库，目录故障不得阻断现有截图识别与求解。
- 浏览器直接访问 API；前端不得代理生产图片上传。生产地址、端口和 CORS 现值见 `STATUS.md`。
- VPS 的 80/443 由共享 Nginx 占用；本项目使用 `deploy/compose.vps.yaml`，API 只绑定回环地址，不启动 Compose 内的 Caddy。
- 后端接口结构变化后，重新导出 `contracts/openapi.json`，再运行 `web/` 中的 `npm run generate:api`，并提交契约与生成类型。
- 前端改动至少运行类型生成和生产构建；后端改动运行相关 pytest；部署配置运行 `docker compose config`；Nginx 变更运行 `nginx -t`。私有样本缺失时必须明确报告跳过，不能声称真实截图识别已验证。
- 前端发布使用带明确 `VITE_API_BASE_URL` 的生产构建和版本化静态目录；不得使用 Vite 开发服务器。发布后检查公网 HTTPS、CORS 和一次实际 API 请求。
- 325 规则或数据变化须通过 `npm run test:calculator`，所有返回方案从原始物品重新复算；限时搜索未穷尽时不得声称无解或全局最优。数据版本、语义与扩展边界见 `docs/calculator-design.md`。
- 325 图标按固定来源表的 `iconId` 关联，媒体更新须通过 `tools/import_calculator_media.py` 审计；图标与来源记录不进入属性计算或 Worker，生产仅使用本站哈希资源。
- 前端界面遵循 `docs/ui-design.md`：样式只用 CSS Modules 和 `ui/` 的 tokens，不再新增全局样式；深浅两主题和 320px 起的宽度都要可用，截图原图和 API 色板不重新着色。
- 界面文案同步简中/英/日/韩并通过 `web/` 的 `npm run test:i18n`；游戏名称更新另跑名称审计。语言切换不得重挂载工具或重提交任务，译文不参与业务判断；哈希语言 JSON 随共享 assets 保留。当前识图语言边界见 STATUS，设计见 `docs/i18n-design.md`。

## 本项目任务记录

- 任务编号沿用 `EW-001` 起的递增编号，每个编号一个章节，按编号递增排列在 `TASK.md`；页首列下一编号及未结任务。
- 查看近期交接使用 `tail -n 160 TASK.md`，按需扩大行数；查更早的具体任务可按编号定位。
