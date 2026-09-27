# 项目当前状态

最后核验：2026-09-27 13:37 UTC。

## 当前阶段

- “浮空回收”已公开部署，支持截图识别、`center-torque-v1` 自动求解、截图范围指引、题号 OCR 与 PostgreSQL 题面目录查询。
- “源石电路”仍为未实现的模块和接口占位。
- 当前生产 release：`ce0d6eed1319db77e2620a0e41075322be7aa9e0`。

## 生产部署

| 项目 | 当前值 |
| --- | --- |
| 前端 | `https://endfield.linbin.org/` |
| 前端 release | `/var/www/endfield-workbench/releases/ce0d6ee`；`current` 指向该目录 |
| API | `https://api.linbin.org/endfield` |
| API 容器 | `endfield-workbench-api-1`，健康，单 Uvicorn worker，重启次数 0 |
| PostgreSQL | `endfield-workbench-db-1`，PostgreSQL 17，健康，重启次数 0，卷 `endfield-workbench_catalog_data` |
| 端口 | API 为 `127.0.0.1:18000` → 容器 `8000`；PostgreSQL `5432` 仅在 Compose 网络内开放 |
| 反向代理 | VPS 现有 Nginx；HTTP 自动跳转 HTTPS |
| 证书 | Let's Encrypt；前端有效至 2026-12-26，API 有效至 2026-12-24 |
| CORS | 仅允许 `https://endfield.linbin.org` |
| 前端 API 地址 | `VITE_API_BASE_URL=https://api.linbin.org/endfield` |
| 目录数据 | 15 个 entry、15 个 candidate、15 个 observation，当前均为 `provisional` |

## 当前验证状态

- 后端全量测试连接真实 PostgreSQL 17：74 passed、5 skipped；跳过项均依赖 VPS 上缺失的 `samples/private/` 旧样本。
- OpenAPI 已重新导出并生成前端类型；前端生产构建、Compose 合并配置与 Nginx 配置检查通过。
- 本机测试集 19 张截图均完成生产 API 识别；18 张得到可行解，15 个完整、可解且带可靠题号的题面写入目录。公开示例 `WL-A1001` 的实际解答通过独立校验。
- 公网题号目录 10 路并发查询均返回 200 且结果一致。数据库与 API 分别重启后，本机和公网健康检查、15 条目录持久化及 `WL-A1001` 查询再次通过。
- HTTP 正确跳转 HTTPS；前端、示例图与 API 均返回 200；生产 Origin 的 CORS 响应正确。
- 空闲快照：API CPU 0.32%、内存 50.13 MiB、9 PIDs；PostgreSQL CPU 0.05%、内存 22.07 MiB、7 PIDs。
- 目录备份：`deploy/backups/catalog-20260927T133434Z.dump`，已通过 `pg_restore --list` 检查且被 Git 忽略。

## 已知限制

- `samples/private/` 中的旧回归样本不在 VPS，相关 5 项测试无法在本机复验。
- 测试图 191530 被识别为不可解的 5×4 题面，因此未写目录；同题号的 191752 能正确识别、求解并写入。目录的可解性校验避免了错误数据覆盖。
- 题目任务与结果仍只保存在单个 API 进程内存中，服务重启后消失。
- 题面目录出现多个候选时会保留并标记 `disputed`，当前没有人工裁决或合并界面。
- 现有 15 条目录记录都只有一个独立图片摘要；需要第二个一致且不同的图片摘要才会升级为 `verified`。
- 网页没有手动编辑识别结果的入口。

## 近期待处理

- 用不同设备或不同截图补充同一题号的独立观察，将可靠目录记录升级为 `verified`。
- 在实际出现 `disputed` 数据后设计管理员裁决与审计流程。
- 继续改善二次缩放和外层界面截图的棋盘识别，不加入单张图片固定像素特例。
