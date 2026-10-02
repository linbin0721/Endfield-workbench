# Endfield Workbench 项目说明

本文件只补充本项目特有约定。通用协作、安全和验证规则遵循 Codex 与 DSH 的全局 `AGENTS.md`。

## 技术栈与目录

- `web/`：React 19、TypeScript、Vite 前端，生产产物为静态文件。
- `web/src/calculator/`：325 挑战计算器的版本化数据、领域模型、属性复算和浏览器 Worker 搜索；`tools/import_calculator_data.py` 为数据导入入口。
- `api/`：FastAPI、OpenCV、RapidOCR、识别器、求解器和内存任务队列。
- `api/app/catalog/`：题号目录规则、PostgreSQL 存储和识别结果对账；原图不落库。
- `contracts/`：后端导出的 OpenAPI 契约；前端类型由此生成。
- `deploy/`：Docker Compose、Caddy 基础配置，以及复用 VPS 现有 Nginx 的 Compose 覆盖配置。
- `docs/`：产品、架构、规则、识别和压测文档；`docs/tasks.md` 保存早期开发验收历史。
- `samples/private/`：不提交的私有识别样本。
- `set/`：根目录下不提交的私有训练/测试样本，当前分为 `set/test set baloons/`（浮空回收回归样本）、`set/train set puzzle/`（源石电路训练样本）、`set/test set puzzel/`（源石电路测试样本）。脚本按实际路径读取；若目录改名，需同步项目内引用。样本原图和派生审计图都不进入 Git。

## 项目约束

- API 任务状态保存在进程内，生产环境必须保持一个 Uvicorn worker，不得横向扩容 API 容器。
- PostgreSQL 只在 Compose 内网提供服务，不发布宿主机端口；目录故障不得阻断现有截图识别与求解。
- 浏览器直接访问 API；前端不得代理生产图片上传。生产地址、端口和 CORS 现值见 `STATUS.md`。
- VPS 的 80/443 由共享 Nginx 占用；本项目使用 `deploy/compose.vps.yaml`，API 只绑定回环地址，不启动 Compose 内的 Caddy。
- 后端接口结构变化后，重新导出 `contracts/openapi.json`，再运行 `web/` 中的 `npm run generate:api`，并提交契约与生成类型。
- 前端改动至少运行类型生成和生产构建；后端改动运行相关 pytest；部署配置运行 `docker compose config`；Nginx 变更运行 `nginx -t`。私有样本缺失时必须明确报告跳过，不能声称真实截图识别已验证。
- 前端发布使用带明确 `VITE_API_BASE_URL` 的生产构建和版本化静态目录；不得使用 Vite 开发服务器。发布后检查公网 HTTPS、CORS 和一次实际 API 请求。
- 325 规则或数据变化须通过 `npm run test:calculator`，所有返回方案从原始物品重新复算；限时搜索未穷尽时不得声称无解或全局最优。数据版本、语义与扩展边界见 `docs/calculator-design.md`。
