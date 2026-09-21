# 首版部署与容量验证设计

2026-09-17 主代理确定，待 T05b 实现和验证。

## 部署边界

- Vercel 只发布 `web/` 的静态构建；浏览器以公开配置的 HTTPS API 地址直连自有服务器。
- Linux 使用 Docker Compose 管理 API 与 Caddy。Caddy 对外提供 HTTPS，API 不发布公网端口。域名与精确的前端 Origin 由部署环境提供，不写入猜测值。
- API 保持一个 Uvicorn 进程，默认两个计算工作进程、八个排队任务、两个同时上传槽位；不能通过增加 Uvicorn workers 扩容。
- 配置容器 CPU、内存、日志轮转及退出等待上限，给宿主机留下余量。初始资源参数是保护边界，不能当作已测容量。
- 图片不永久保存；反向代理不要开启请求完整缓冲或记录请求体。API 上传与像素限制仍负责实际处理边界。
- Caddy 证书数据使用持久卷。实际签发需要真实域名解析和公网端口条件；本机配置验证不能替代线上验收。

## 压测边界

分别对真实求解和真实图片识别进行 100 个同时发起的请求测试。记录提交成功、429 拒绝、其他错误、任务最终状态、结果 outcome、提交延迟、端到端时间，以及服务进程树的内存和 CPU 采样。测量 API 健康检查在计算期间是否仍可响应。

默认保护策略不承诺接收全部 100 个请求；不能把 429 算作计算成功，也不能把 HTTP 202 算作解题完成。识别必须使用真实截图，缺少图片时明确不能执行该项。

负载程序与服务分开统计。进程 RSS 求和可能重复计算共享内存，采样会漏过短暂峰值，报告应明确测量方法。CPU 可用一核 100% 的进程树口径，不混同整机百分比。测试运行机、工作进程数、队列大小和输入大小随结果记录。

本机环回测试不能测出香港服务器的 E5 算力、20 Mbps 链路或大陆访问体验。购买后的容量调整需要在目标服务器重跑同一脚本；100 人在线与 100 个同时提交计算是不同负载。

## 已查阅的官方配置依据

- [Docker Compose 服务选项](https://docs.docker.com/reference/compose-file/services/)：资源限制、init、退出等待和健康检查。
- [Caddy 反向代理](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)：不启用 request_buffers。
- [Caddy 自动 HTTPS](https://caddyserver.com/docs/automatic-https) 与 [HTTPS 起步条件](https://caddyserver.com/docs/quick-starts/https)：证书签发和公网部署条件。

没有 Docker daemon 时只能检查配置和本机应用，不能报告镜像已构建或 Linux 部署已验证。
