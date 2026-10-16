# 网页本地运行

需要 Node.js 20.19+。先在 `api/` 启动单进程 API，再从 `web/` 运行：

```powershell
npm ci
Copy-Item .env.example .env.local
npm run generate:api
npm run dev
```

打开 `http://localhost:5173`。如 API 不在本机，请将 `.env.local` 中的 `VITE_API_BASE_URL` 改为自有 API 的公开 HTTPS 地址；它是浏览器直接访问的地址，不能填密钥。后端 `CORS_ORIGINS` 必须包含网页实际域名。Vercel 项目根目录设为 `web`，配置同一个公开环境变量即可。静态托管不代理 API 请求。

验证生产包：

```powershell
npm run generate:api
npm run build
```

两种解谜都接入真实 API。选择图片、预览和手动裁剪都在浏览器内进行；点击“识别并求解”才把当前选定范围直传自有 API（整图上传原文件，裁剪时上传 PNG，均不超过 12 MB）。识别出完整题面时自动求解；缺数字或数据不一致时停在题面步并标红，补全或修改后再求解。题号查询得到的目录题面只读。

页面流程、状态与测试钩子见 [`docs/frontend-flow.md`](../docs/frontend-flow.md)，界面风格、设计令牌、主题与组件约定见 [`docs/ui-design.md`](../docs/ui-design.md)。
