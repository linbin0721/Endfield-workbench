# 四语界面

## 范围与边界

首页、浮空回收、源石电路、325 支持简中、英语、日语、韩语，包括名称、运行提示、复制和无障碍标签。示例图片像素保持原样；当前 OCR 只在简中截图上核验，其他语言识图单独开发。

语言路由是 `/:locale` 及三条工具子路由，无前缀地址保留为兼容入口。URL 优先于保存偏好和浏览器语言；语言选择器用各语言自身名称。Nginx 原有 SPA 回退支持深链，API/CORS 无需变化。

## 保留正在运行的工具

- 语言变化只更新同一路由的参数，不重挂载页面，不清空截图/裁剪/条件/结果，也不重新提交任务或启动 Worker。
- 提示状态保存 `{key, ns, params}` 或原始接口字符串，在渲染时翻译；复制在点击时按当前语言生成。
- 原始中文“推导”过滤、已摆放判断、数值复算、独立校验及指纹不读取译文。保持当前 API/Worker 契约，以展示兼容层承接已有字符串。
- 兼容层按原文模板提取数字/题号、翻译嵌套原因；未知消息在非中文界面提示可切简中查看原文。以后可演进为结构化消息代码，但必须同时维护旧版本兼容。

## 语言资源与发布

资源位于 `web/src/i18n/locales/`，按页面分 namespace。Vite 输出独立哈希 JSON，主包只包含 URL 表；仅 fetch 当前需要的语言和模块，`names` 不进入首页/Worker。

使用 fetch 而非直接动态 import 语言模块：真实失败注入中，浏览器缓存了失败的 ES module 导入，普通重试无法恢复。fetch 失败可重新请求，10 秒期限覆盖响应与 JSON；选择失败保留原页，新工具进入失败有重试，初始失败有重新加载入口。

JSON 与 JS/CSS 一样进入本站跨 release 共享 assets，保留旧哈希；不使用固定 `public/locales/*.json` URL。参考 [Vite 资源处理](https://vite.dev/guide/assets)、[react-i18next hook](https://react.i18next.com/latest/usetranslation-hook)。

## 游戏名称与数据版本

固定版本 `1.5.3/10506507-7`，名称来自 AKEData 公开的该版本 `ItemTable`、`EquipSuitTable` 和 CN/EN/JP/KR 文本表：

- 四语各覆盖 33 干员、80 武器、258 装备、4 套装，按 ID 关联。
- 中文输出必须等于现有数值快照的名称。男女管理员后缀是本站为区分记录添加的标注。
- 64 位文本 ID 用 Python 解析，避免 JavaScript Number 精度丢失；禁止按中文名或图片外观猜对应项。
- 原表留在 Git 忽略缓存；版本、来源 URL、输入/输出 SHA-256 记录于 `game-names-provenance.json`。名称、媒体与数值计算分离；数据版本更新时同步重新导入。

```bash
cd /root/project/EndfieldWorkbench
python3 tools/import_calculator_names.py --cache deploy/.local-backups/ew025-language-tables --download
python3 tools/import_calculator_names.py --audit
cd web
npm run test:i18n
npm run test:calculator
npm run generate:api
VITE_API_BASE_URL=https://api.linbin.org/endfield npm run build
```

资源审计检查完整键、插值、中文泄漏和消息匹配；名称审计独立检查全量 ID、版本与哈希。浏览器验收须覆盖语言深链、返回/前进、正在处理时切语、失败重试、四语复制和窄屏。四语界面通过不代表四语 OCR 已通过。
