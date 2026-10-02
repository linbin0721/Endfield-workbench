# Endfield Workbench

面向《明日方舟：终末地》的非官方开源工具项目。支持“浮空回收”和“源石电路”截图识别、题号查询与自动求解，以及四维属性 325 挑战计算器。

> 本项目由玩家独立开发，与鹰角网络、Hypergryph 或《明日方舟：终末地》官方无关。游戏名称、画面及相关商标归各自权利人所有。

## 当前功能

- 从 PNG、JPEG 或 WebP 截图中识别完整棋盘和右侧气球库存。
- 支持电脑选择、拖放、粘贴图片，以及手机相册选图。
- 默认上传完整原图并自动定位棋盘，也可在浏览器中手动裁剪识别范围。
- 按 `center-torque-v1` 规则自动求解，并独立校验返回的摆放方案。
- 对无解、搜索超时、识别失败、任务取消和队列已满等情况给出明确结果。
- 使用有界任务队列、上传大小与像素限制，识别过程不持久化原图。
- 识别“源石电路”的行列覆盖约束、障碍、固定格和库存拼块，并按 `line-count-v1` 返回经过独立校验的摆放方案。
- 325 挑战：选择干员、等级和潜能，在养成上限内查找常驻面板方案，优先多项属性显示 325；浏览器独立线程计算，不占识别队列。

当前网页流程是“一次点击，先识别再求解”。当库存数字不完整或题面不能可靠识别时，网页会要求更换清晰完整的截图；当前没有手动编辑识别结果的入口。

网页首页可分别进入 `/balloon` 和 `/circuit`；两个谜题均支持截图流程与按题号查询。这里描述的是当前代码能力，不代表尚未执行的生产发布已经完成。

计算器位于 `/325`，默认提弗洛斯、满级、0 潜能，支持任意潜能搜索及装备/武器/基质养成限制。数据为版本化公开快照，结果需在游戏内核对；限时搜索未找到方案不代表无解。公式、数据来源、更新与扩展说明见 [计算器设计](docs/calculator-design.md)。

## 支持的规则

浮空回收使用 `center-torque-v1`：以矩形棋盘的几何中心为支点，每个气球的升力分别乘以它到中心的行、列距离，左右和上下的加权升力需要各自平衡。每格最多放置一个气球，并使用全部库存。

源石电路使用 `line-count-v1`：每个颜色通道分别满足逐行、逐列覆盖数；障碍格不可覆盖，固定格计入约束；全部库存拼块均可旋转且必须使用。

求解器支持 2–6 行、2–6 列，最多 18 个气球。它会返回一组经校验的可行解，或明确返回无解、计算限额结果。达到计算限额并不代表题目无解。

## 技术栈与目录

- `web/`：React 19、TypeScript、Vite 静态网页。
- `api/`：Python、FastAPI、OpenCV、RapidOCR，以及气球识别和求解模块。
- `contracts/`：由后端导出的 OpenAPI 文档；前端类型由它生成。
- `deploy/`：Docker Compose 与 Caddy 的 Linux 部署配置。
- `docs/`：产品范围、架构、规则依据、实现记录和本机压测报告。
- `web/src/calculator/` 与 `tools/import_calculator_data.py`：计算器领域逻辑及公开数据导入。
- `samples/private/`：仅供本地识别回归测试使用的私有截图，已被 Git 忽略。

浏览器会直接请求 API。静态网页不代理图片上传或计算请求，生产环境需要为 API 提供 HTTPS 地址，并正确配置 CORS。

## 本地运行

需要：

- Python 3.11 或更高版本
- Node.js 20.19 或更高版本

### 1. 启动 API

在 PowerShell 中进入 `api/`：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:CORS_ORIGINS = "http://localhost:5173"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

API 的任务队列和结果保存在单个进程内，因此本地与当前部署配置都应使用一个 Uvicorn worker。

### 2. 启动网页

另开一个 PowerShell 窗口，进入 `web/`：

```powershell
npm ci
Copy-Item .env.example .env.local
npm run generate:api
npm run dev
```

然后访问 `http://localhost:5173`。首页位于 `/`，浮空回收位于 `/balloon`，源石电路位于 `/circuit`。默认示例配置会连接 `http://localhost:8000`。

## 验证

后端测试：

```powershell
cd api
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

前端生产构建：

```powershell
cd web
npm ci
npm run generate:api
npm run build
```

计算器测试（Node.js 22.18+，利用内置 TypeScript 类型擦除）：

```bash
cd web
npm run test:calculator
```

真实截图回归测试会在本地存在对应私有样本时运行；缺少样本时会明确跳过。因此，仅凭测试通过不能证明识别器适用于任意截图或拍屏照片。

## 项目状态与限制

项目仍处于早期阶段：

- 浮空回收的本地识别、求解和响应式网页流程已经实现并经过现有样本与测试验证。
- 当前样本数量有限，识别效果会受截图完整度、清晰度、缩放和拍摄角度影响。
- 生产网页为 `https://endfield.linbin.org/`，浏览器直接访问 VPS HTTPS API；当前发布与验证事实见 [STATUS.md](STATUS.md)。
- 本机 100 并发报告验证了限流行为，不代表服务器可同时接受 100 个识别任务，也不能代表未来生产环境容量。
- 任务与结果仅保存在 API 进程内，会因过期、保留数量限制或服务重启而消失。

详细记录见 [项目任务与验收](docs/tasks.md)、[总体架构](docs/architecture.md)、[识别实现说明](docs/mobile-recognition-implementation.md) 和 [本机压测报告](docs/benchmarks/README.md)。部署前请阅读 [Linux 部署说明](deploy/README.md)。

## 隐私

选择图片和预览都发生在浏览器本地。只有点击“识别并求解”后，当前选择的完整图片或裁剪结果才会上传到配置的 API。API 对单张图片限制为 12 MiB、解码后最多 2000 万像素；当前实现不持久化上传的原图。

请不要把含有个人信息的截图作为公开测试样本提交。仓库已忽略 `samples/private/`。

## 贡献

欢迎通过 Issue 报告可复现的问题，或通过 Pull Request 提交修复。提交识别问题时，请先确认截图中包含完整棋盘和右侧全部库存；公开上传截图前请自行检查其中是否含有个人信息。

## 许可证

代码以 [MIT License](LICENSE) 发布。游戏截图、名称、标志和其他第三方素材不因本仓库的代码许可证而获得授权。
