# 项目当前状态

最后核验：2026-09-29 07:45 UTC。

## 当前阶段

- “浮空回收”和“源石电路”均已公开部署。两者都支持截图识别、自动求解和按题号查询；网页入口分别为 `/balloon` 与 `/circuit`。
- 当前生产源码提交为 `90b762f2231a205e27d8b6a7c6380d0130c499a5`，EW-006 A～E 已验收。
- EW-007 批次 A 已验收，识别真实色相、目录色板、旧表迁移和 API 契约已完成；当前批次 B 处理前端颜色流转与完成棋盘，生产服务仍保持 EW-006 release，尚未包含这次视觉重构。
- 源石电路私有训练集现有 37 张，测试集 3 张；当前支持短条、数字和罗马数字约束、1～4 通道、障碍、固定格及可旋转库存拼块。

## 生产部署

| 项目 | 当前值 |
| --- | --- |
| 前端 | `https://endfield.linbin.org/` |
| 前端 release | `/var/www/endfield-workbench/releases/90b762f`；`current` 指向该目录 |
| API | `https://api.linbin.org/endfield` |
| API 容器 | `endfield-workbench-api-1`，镜像 `sha256:bb9cf0ec…`，健康，单 Uvicorn worker，异常重启次数 0 |
| PostgreSQL | `endfield-workbench-db-1`，PostgreSQL 17，健康，异常重启次数 0，卷 `endfield-workbench_catalog_data` |
| 端口 | API 为 `127.0.0.1:18000` → 容器 `8000`；PostgreSQL `5432` 仅在 Compose 网络内开放 |
| 反向代理 | VPS 共享 Nginx；HTTP 自动跳转 HTTPS；本次发布未修改配置 |
| 证书 | Let's Encrypt；前端有效至 2026-12-26，API 有效至 2026-12-24 |
| CORS | 仅允许 `https://endfield.linbin.org` |
| 前端 API 地址 | `VITE_API_BASE_URL=https://api.linbin.org/endfield` |
| 气球目录 | 15 个 entry、15 个 candidate、16 个 observation；14 个 `provisional`、1 个 `verified` |
| 电路目录 | 1 个 entry、1 个 candidate、1 个 observation；`V40020` 为 `provisional` |
| 发布前备份 | `deploy/backups/catalog-20260929T052718Z.dump`，已通过 `pg_restore --list` |

## 当前验证状态

- 后端全量连接临时 PostgreSQL 17：674 passed、6 skipped、1 个既有弃用警告；跳过项均依赖 VPS 缺失的旧 `samples/private/` 气球图片。OpenAPI 与前端生成类型可重复，生产前端构建 60 modules。
- 40 张源石电路私有原图回归为 21 `recognized/bars`、18 `already_completed/bars`、1 `recognized/digits`，失败 0，题号命中 36/40；所有完整题面重新求解并独立校验，数字/短条 `V40020` 一致。
- 公网真实源石电路截图识别、求解与 `V40020` 题号查询成功；公网浮空回收 191530 识别为 5×5 `WL-A2014`、库存 6×1 + 3×1，并求解成功。两类公网解答都再次通过独立校验器。
- API 与数据库分别主动重启后容器恢复健康，六张目录表保持气球 15/15/16、电路 1/1/1。数据库重启后的第一次目录请求返回一次 503，下一请求立即恢复。
- 公网 10 路并发求解全部接受并完成：10 个 202、10 个 solved，无 429、5xx、传输或轮询错误，P95 端到端约 941 ms；健康采样全为 200。
- Edge 154 中首页、`/balloon`、`/circuit` 深链和刷新正常；网页题号 `V40020` 自动绘制 25 格答案与 4 个拼块摆放。1440×900 和 390×844 无横向溢出，键盘焦点可见。
- HTTPS 证书、HTTP 301、生产 Origin CORS、非允许 Origin 拒绝、Compose 配置、Nginx 配置和回环端口检查均通过。
- 空闲快照：API CPU 0.21%、内存 92.08 MiB；PostgreSQL CPU 0.01%、内存 21.98 MiB。

## 已知限制

- 源石电路测试集仅 3 张，其中 `WL0020` 与训练集存在题目级重叠，不能视为完全独立的最终评估集；数字模式真实样本仍只有 `V40020` 一题。
- `samples/private/` 中的旧气球回归样本不在 VPS，相关 6 项测试无法在本机复验。
- 任务与结果只保存在单个 API 进程内存中，服务重启后会消失。
- PostgreSQL 主动重启后的首个目录请求可能短暂返回一次 503；下一请求会重建连接并恢复，截图识别和求解不受影响。
- 浮空回收目录出现多个题面候选时会标记 `disputed`，当前没有管理员裁决或合并界面。
- 网页没有手动编辑识别结果的入口。

## 近期待处理

- 补充不同设备、不同缩放和更多数字/罗马约束的源石电路截图，并保持原图不进入 Git。
- 为现有 `provisional` 目录记录补充不同图片摘要，使可靠候选升级为 `verified`。
- 若需要数据库重启期间目录请求无感恢复，在目录存储层加入一次受限重试并补生产等价回归。
