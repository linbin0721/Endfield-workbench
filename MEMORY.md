# 项目长期记忆

本文件只保存未来跨 Session 仍需理解的信息。当前运行事实见 `STATUS.md`，任务交接与一次性结果见 `TASK.md`。

## 架构决策及原因

- 前端当前采用 VPS 静态托管，便于 Codex 与 DSH 在同一环境完成构建、发布和验证。前端仍通过公开 HTTPS 地址直接请求 API，因此以后迁移到 Vercel 时不需要改变上传链路。
- 多个项目共用 `api.linbin.org`，Endfield Workbench 使用 `/endfield` 前缀。Nginx 转发时移除该前缀，FastAPI 内部继续使用原有 `/api/v1/...` 路径，避免为部署前缀改写应用路由和 OpenAPI 契约。
- VPS 已有 Nginx 管理多个站点并占用 80/443，因此生产部署使用 `compose.yaml` 与 `compose.vps.yaml` 叠加，只发布回环端口，不启用仓库内的 Caddy 服务。
- API 的队列、任务状态和结果都在进程内存中。为了保证任务查询总能命中同一状态，生产必须保持一个 Uvicorn worker，也不能扩成多个 API 容器。
- OpenAPI 的权威来源是后端应用；`contracts/openapi.json` 是前后端之间的版本化契约，`web/src/generated/api.ts` 由它生成，不能手工维护生成类型。

## 长期兼容要求

- 浏览器必须直接向 VPS API 上传图片，不能让生产图片绕经静态前端或 Vercel。
- 前端 API 基址允许包含 `/endfield` 前缀，但不能带末尾斜杠；前端会在其后追加 `/api/v1/...`。
- API 的上传大小、像素、队列和计算限制属于防止 OCR 与求解耗尽服务器资源的生产边界，修改时需同时核对代理层和应用层限制。
- 上传原图当前不持久化；引入持久化前必须重新评估隐私、保留期限和访问控制。
- “源石电路”仅声明未实现；在规则、模型和验收样本明确前，不应复用“浮空回收”的假设补齐功能。

## 已知坑与背景

- VPS 环境设置了 `NODE_ENV=production`，直接运行 `npm ci` 会遗漏 TypeScript、Vite 等构建依赖；在服务器构建前端时使用 `npm ci --include=dev`。
- `samples/private/` 被 Git 忽略且不会随仓库部署。缺少这些样本时，测试通过只能证明公开测试覆盖的逻辑，不能证明真实截图 OCR 准确率。
- 共享 Nginx 还承载其他项目；本项目的代理或证书变更必须限定在自己的站点配置中。
- GitHub 自动推送使用本仓库专用的可写 Deploy Key；该密钥不能复用于其他仓库。
