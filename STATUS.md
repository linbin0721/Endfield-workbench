# 项目当前状态

最后核验：2026-09-27 11:05 UTC。

## 当前阶段

- “浮空回收”MVP 已公开部署，支持截图识别与 `center-torque-v1` 自动求解。
- “源石电路”仍为未实现的模块和接口占位。
- 当前生产 release：`4e8d18745fe1219bb28d242aa0169012dcf0bae0`。

## 生产部署

| 项目 | 当前值 |
| --- | --- |
| 前端 | `https://endfield.linbin.org/` |
| 前端 release | `/var/www/endfield-workbench/releases/4e8d18745fe1`；`current` 指向该目录 |
| API | `https://api.linbin.org/endfield` |
| API 容器 | `endfield-workbench-api-1`，健康，单 Uvicorn worker，重启次数 0 |
| 内部端口 | `127.0.0.1:18000` → 容器 `8000` |
| 反向代理 | VPS 现有 Nginx；HTTP 自动跳转 HTTPS |
| 证书 | 前端证书有效至 2026-12-26；API 证书有效至 2026-12-24；Certbot timer 正常 |
| CORS | 仅允许 `https://endfield.linbin.org` |
| 前端 API 地址 | `VITE_API_BASE_URL=https://api.linbin.org/endfield` |

## 当前验证状态

- 前端 OpenAPI 类型生成和生产构建通过；线上首页、静态资源和 API 健康检查返回 200。
- 后端测试：24 passed、5 skipped；跳过项均依赖缺失的私有截图样本。
- OpenAPI 导出与仓库契约一致；Compose 与 Nginx 配置检查通过。
- 生产 CORS 允许来源与拒绝来源均已检查；一次公网求解请求成功并独立核对平衡结果。
- 前端证书模拟续期成功。

## 已知限制

- VPS 没有真实私有截图样本，真实截图 OCR 尚未在该服务器验证。
- API 任务与结果仅保存在单进程内存中，服务重启后消失。
- 网页没有手动编辑识别结果的入口。
- `README.md` 和部分 `deploy/README.md` 仍包含部署前状态或 Vercel 方案描述。

## 近期待处理

- 使用合规的真实截图验证 VPS 上的 OCR 流程。
- 更新与当前 VPS 前端部署不一致的公开文档。
