# 项目当前状态

最后核验：2026-09-27 11:55 UTC。

## 当前阶段

- “浮空回收”MVP 已公开部署，支持截图识别与 `center-torque-v1` 自动求解。
- “源石电路”仍为未实现的模块和接口占位。
- 当前生产 release：`917fd79a0a0d05702bfb2026d652901fd97e22b4`。

## 生产部署

| 项目 | 当前值 |
| --- | --- |
| 前端 | `https://endfield.linbin.org/` |
| 前端 release | `/var/www/endfield-workbench/releases/917fd79`；`current` 指向该目录 |
| API | `https://api.linbin.org/endfield` |
| API 容器 | `endfield-workbench-api-1`，健康，单 Uvicorn worker，重启次数 0 |
| 内部端口 | `127.0.0.1:18000` → 容器 `8000` |
| 反向代理 | VPS 现有 Nginx；HTTP 自动跳转 HTTPS |
| 证书 | 前端证书有效至 2026-12-26；API 证书有效至 2026-12-24；Certbot timer 正常 |
| CORS | 仅允许 `https://endfield.linbin.org` |
| 前端 API 地址 | `VITE_API_BASE_URL=https://api.linbin.org/endfield` |

## 当前验证状态

- 前端生产构建通过；线上首页加载 `index-vWboGmSb.js`，静态页面与 API 健康检查返回 200。
- 后端测试：34 passed、5 skipped；跳过项均依赖缺失的 `samples/private/` 旧样本。
- OpenAPI 导出与仓库契约一致；Compose 与 Nginx 配置检查通过。
- 本地 `test set/` 的 5 张截图已重跑：4 张可识别并求解；两张四行库存图的第四行被唯一推导为升力 1 × 3。公网实际上传其中一张后，识别、求解和独立平衡校验均通过。
- 生产 CORS 允许 `https://endfield.linbin.org` 并拒绝未知来源；HTTP 跳转 HTTPS，证书有效期未变化。
- 发布后 API 容器健康、重启次数 0；一次空闲快照为 CPU 0.83%、内存 43.23 MiB、4 PIDs。
- 前端证书模拟续期成功。

## 已知限制

- `samples/private/` 中的旧回归样本仍不在 VPS，相关 5 项测试无法在本机复验。
- `test set/` 的 191530 是二次缩放并带外层界面的截图；当前能读出升力 6、3，但两个数量都缺失，按严格规则拒绝推导和求解。
- API 任务与结果仅保存在单进程内存中，服务重启后消失。
- 网页没有手动编辑识别结果的入口。
- `README.md` 和部分 `deploy/README.md` 仍包含部署前状态或 Vercel 方案描述。

## 近期待处理

- 有旧私有样本时复验其第四行 `1×3` 推导结果。
- 评估是否要改善二次缩放截图的库存图标定位；不得为单张图加入固定像素特例。
- 更新与当前 VPS 前端部署不一致的公开文档。
