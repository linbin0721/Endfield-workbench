# Endfield Workbench 项目说明

本文件只补充本项目特有约定。通用协作、安全和验证规则遵循 Codex 与 DSH 的全局 `AGENTS.md`。

## 技术栈与目录

- `web/`：React 19、TypeScript、Vite 前端，生产产物为静态文件。
- `api/`：FastAPI、OpenCV、RapidOCR、识别器、求解器和内存任务队列。
- `contracts/`：后端导出的 OpenAPI 契约；前端类型由此生成。
- `deploy/`：Docker Compose、Caddy 基础配置，以及复用 VPS 现有 Nginx 的 Compose 覆盖配置。
- `docs/`：产品、架构、规则、识别和压测文档；`docs/tasks.md` 保存早期开发验收历史。
- `samples/private/`：不提交的私有识别样本。

## 项目约束

- API 任务状态保存在进程内，生产环境必须保持一个 Uvicorn worker，不得横向扩容 API 容器。
- 浏览器直接访问 API；前端不得代理生产图片上传。生产地址、端口和 CORS 现值见 `STATUS.md`。
- VPS 的 80/443 由共享 Nginx 占用；本项目使用 `deploy/compose.vps.yaml`，API 只绑定回环地址，不启动 Compose 内的 Caddy。
- 后端接口结构变化后，重新导出 `contracts/openapi.json`，再运行 `web/` 中的 `npm run generate:api`，并提交契约与生成类型。
- 前端改动至少运行类型生成和生产构建；后端改动运行相关 pytest；部署配置运行 `docker compose config`；Nginx 变更运行 `nginx -t`。私有样本缺失时必须明确报告跳过，不能声称真实截图识别已验证。
- 前端发布使用带明确 `VITE_API_BASE_URL` 的生产构建和版本化静态目录；不得使用 Vite 开发服务器。发布后检查公网 HTTPS、CORS 和一次实际 API 请求。
