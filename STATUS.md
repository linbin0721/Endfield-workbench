# 项目当前状态

最后核验：2026-09-28 10:48 UTC。

## 当前阶段

- “浮空回收”已公开部署，支持截图识别、`center-torque-v1` 自动求解、截图范围指引、题号 OCR 与 PostgreSQL 题面目录查询；首页先选择入口，再展开对应流程。
- “源石电路”仍未实现；开发样本已接收并完成完整性审计：34 张训练图组成 17 组题面/答案，另有 3 张测试题面。
- 当前前端提交：`56256c94aa1fcba5b98f9871abe720e2e00767c0`。
- 当前 API 生产 release：`33cd3502c0a5b074ca83419a645ea396618de19c`。

## 生产部署

| 项目 | 当前值 |
| --- | --- |
| 前端 | `https://endfield.linbin.org/` |
| 前端 release | `/var/www/endfield-workbench/releases/56256c9`；`current` 指向该目录 |
| API | `https://api.linbin.org/endfield` |
| API 容器 | `endfield-workbench-api-1`，健康，单 Uvicorn worker，重启次数 0 |
| PostgreSQL | `endfield-workbench-db-1`，PostgreSQL 17，健康，重启次数 0，卷 `endfield-workbench_catalog_data` |
| 端口 | API 为 `127.0.0.1:18000` → 容器 `8000`；PostgreSQL `5432` 仅在 Compose 网络内开放 |
| 反向代理 | VPS 现有 Nginx；HTTP 自动跳转 HTTPS |
| 证书 | Let's Encrypt；前端有效至 2026-12-26，API 有效至 2026-12-24 |
| CORS | 仅允许 `https://endfield.linbin.org` |
| 前端 API 地址 | `VITE_API_BASE_URL=https://api.linbin.org/endfield` |
| 目录数据 | 15 个 entry、15 个 candidate、16 个 observation；14 个 `provisional`、1 个 `verified` |

## 当前验证状态

- 后端全量测试连接真实 PostgreSQL 17：78 passed、5 skipped；跳过项均依赖 VPS 上缺失的 `samples/private/` 旧样本。
- OpenAPI 已重新导出并生成前端类型；前端生产构建、Compose 合并配置与 Nginx 配置检查通过。
- 本机测试集 19 张截图均完成真实识别入口回归；修复后 191530 与 191752 都识别为相同的 5×5 `WL-A2014` 题面并通过独立求解校验，其他 17 张没有回退。
- 公网上传 191530 后得到 5×5、库存 6×1 + 3×1、目标 9；公网求解返回两个气球的平衡解，行列力矩均为 0。该图片作为第二个不同摘要把 `WL-A2014` 升级为 `verified`，仍只有一个候选、观察数为 2。
- 公网题号目录 10 路并发查询均返回 200 且结果一致。数据库与 API 分别重启后，本机和公网健康检查、15 条目录持久化及 `WL-A1001` 查询再次通过。
- HTTP 正确跳转 HTTPS；前端、示例图与 API 均返回 200；生产 Origin 的 CORS 响应正确。
- 前端入口与示例布局已在 1440×900 和 390×844 两种视口通过公网浏览器检查：初始不展开流程，截图与题号分支顺序正确，切换后不保留旧图片，题号标记不遮挡原图编号；生产构建通过。
- 空闲快照：API CPU 0.40%、内存 73.38 MiB；PostgreSQL CPU 1.44%、内存 22.57 MiB。
- 目录备份：`deploy/backups/catalog-20260927T133434Z.dump`，已通过 `pg_restore --list` 检查且被 Git 忽略。

## 已知限制

- 源石电路测试集仅 3 张，其中 `△-WL0020` 与训练集存在题目级重叠，不能把当前测试集视为完全独立的最终评估集。
- `samples/private/` 中的旧回归样本不在 VPS，相关 5 项测试无法在本机复验。
- 题目任务与结果仍只保存在单个 API 进程内存中，服务重启后消失。
- 题面目录出现多个候选时会保留并标记 `disputed`，当前没有人工裁决或合并界面。
- 除 `WL-A2014` 外的 14 条目录记录都只有一个独立图片摘要，仍为 `provisional`。
- 网页没有手动编辑识别结果的入口。

## 近期待处理

- 明确源石电路的网格、行列约束、障碍格、可旋转拼块和完成条件，再定义识别契约、求解模型及独立验收集。
- 用不同设备或不同截图补充其余题号的独立观察，将可靠目录记录升级为 `verified`。
- 在实际出现 `disputed` 数据后设计管理员裁决与审计流程。
- 继续收集二次缩放和外层界面截图作为棋盘定位回归样本，不加入单张图片固定像素特例。
