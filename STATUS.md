# 项目当前状态

最后核验：2026-09-29 18:11 UTC。

## 当前阶段

- “浮空回收”和“源石电路”均已公开部署。两者都支持截图识别、自动求解和按题号查询；网页入口分别为 `/balloon` 与 `/circuit`。
- 当前生产前端提交为 `a6fe91b6c943309e14022b2d50098836c1b23ac4`，API 提交为 `4056d5e7c8c53e0e1c5e5c408435b81c92107d60`；EW-010 已验收并发布。
- 源石电路截图识别会保留真实色相；截图、题号目录与 legacy 候选都能把正确色板带到答案。每个库存形状使用一个整体路径和连续渐变，不显示内部格线、通道/拼块编号、坐标、旋转或约束清单。
- 源石电路截图与题号入口共用同一张未解题示意画面；约束已从示例中移除，题号、棋盘和库存由三个编号区域标出。库存形状使用与答案相同的整体 SVG 路径、连续渐变和外轮廓。
- 源石电路私有训练集现有 37 张，测试集 3 张；当前支持短条、数字和罗马数字约束、1～4 通道、障碍、固定格及可旋转库存拼块。

## 生产部署

| 项目 | 当前值 |
| --- | --- |
| 前端 | `https://endfield.linbin.org/` |
| 前端 release | `/var/www/endfield-workbench/releases/a6fe91b`；`current` 指向该目录 |
| API | `https://api.linbin.org/endfield` |
| API 容器 | `endfield-workbench-api-1`，镜像 `sha256:0dc5433b…`，健康，单 Uvicorn worker，异常重启次数 0 |
| PostgreSQL | `endfield-workbench-db-1`，PostgreSQL 17，健康，异常重启次数 0，卷 `endfield-workbench_catalog_data` |
| 端口 | API 为 `127.0.0.1:18000` → 容器 `8000`；PostgreSQL `5432` 仅在 Compose 网络内开放 |
| 反向代理 | VPS 共享 Nginx；HTTP 自动跳转 HTTPS；本次发布未修改配置 |
| 证书 | Let's Encrypt；前端有效至 2026-12-26，API 有效至 2026-12-24 |
| CORS | 仅允许 `https://endfield.linbin.org` |
| 前端 API 地址 | `VITE_API_BASE_URL=https://api.linbin.org/endfield` |
| 气球目录 | 15 个 entry、15 个 candidate、16 个 observation；14 个 `provisional`、1 个 `verified` |
| 电路目录 | 1 个 entry、1 个 candidate、1 个 observation；`V40020` 为 `provisional`，候选已有 1 通道展示色板 |
| 发布前备份 | `deploy/backups/circuit-before-ew007-20260929T085002Z.dump`，已通过 `pg_restore --list` |

## 当前验证状态

- EW-007 后端全量连接临时 PostgreSQL 17：712 passed、5 skipped；独立复跑无数据库全量为 698 passed、19 skipped。跳过项来自未设置测试数据库及 VPS 缺失的旧 `samples/private/` 气球图片。OpenAPI/生成类型哈希稳定；生产前端构建 61 modules。
- 40 张源石电路私有原图回归为 21 `recognized/bars`、1 `recognized/digits`、18 `already_completed`，失败 0；22 个完整题面均输出完整色板，输入与对应完成画面的同通道色差最大 5.45°，题号命中保持 36/40。
- 公网数字版 `V40020` 真实截图识别为 77.04° 绿色并求解成功，结果再次通过独立校验器；legacy 目录候选已安全补色，API 重启后仍可查询。公网题号流程绘制 5×5 完成棋盘、4 个独立库存形状和 2 个障碍。
- Edge 154 中 `/circuit` 深链和刷新正常；1440×900 与 390×844 无横向溢出，输入焦点为 2px 实线。答案区域没有 `C1`/`P1`、坐标、旋转或约束文字。
- EW-008 公网 DOM 验证 V40020 的 4 个 placement 各有 1 个整体 fill path、0 个逐格 rect、2 个独立外轮廓；7/3/4/4 格形状的 user-space 渐变范围分别与自身包围盒一致，桌面和移动端目视无格状重复或内部缝隙。
- EW-010 公网 Edge 验证两种入口的示意 stage 完全一致：约束节点为 0，编号区域为 `3/1/2`，三组库存各有 1 个整体 SVG fill path、0 个 rect 和 2 个外轮廓 path。1440×900 与 390×844 均无重叠或横向溢出，console/runtime error 为 0。
- 公网 10 路并发目录查询均为 HTTP 200；API 主动重启后健康、目录色板与题号求解正常。
- HTTPS 证书、HTTP 301、生产 Origin CORS、非允许 Origin 拒绝、Compose 配置、Nginx 配置和回环端口检查均通过。
- 空闲快照：API CPU 0.22%、内存 51.72 MiB；PostgreSQL CPU 0.00%、内存 28.68 MiB。

## 已知限制

- 源石电路测试集仅 3 张，其中 `WL0020` 与训练集存在题目级重叠，不能视为完全独立的最终评估集；数字模式真实样本仍只有 `V40020` 一题。
- 40 张私有样本的题号 OCR 命中率为 36/40；其中训练图 `183630` 的 `WL0020` 仍未读出，但题面与颜色识别成功，可继续直接求解。
- `samples/private/` 中的旧气球回归样本不在 VPS，相关 6 项测试无法在本机复验。
- 任务与结果只保存在单个 API 进程内存中，服务重启后会消失。
- PostgreSQL 主动重启后的首个目录请求可能短暂返回一次 503；下一请求会重建连接并恢复，截图识别和求解不受影响。
- 浮空回收目录出现多个题面候选时会标记 `disputed`，当前没有管理员裁决或合并界面。
- 网页没有手动编辑识别结果的入口。

## 近期待处理

- 补充不同设备、不同缩放和更多数字/罗马约束的源石电路截图，并保持原图不进入 Git。
- 为现有 `provisional` 目录记录补充不同图片摘要，使可靠候选升级为 `verified`。
- 若需要数据库重启期间目录请求无感恢复，在目录存储层加入一次受限重试并补生产等价回归。
