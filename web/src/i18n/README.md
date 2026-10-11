# 界面语言

支持 `zh-CN / en / ja / ko`。每种语言维护 `common / messages / balloon / circuit / calculator / names` 六份 JSON。截图识别语言目前不随界面变化。

## 路由与资源

- 使用 `/:locale`、`/:locale/balloon`、`/:locale/circuit`、`/:locale/325`；原四条无前缀地址自动跳转并保留 query/hash。优先级为 URL → 保存偏好 → 浏览器语言 → 简中。
- Vite `import.meta.glob` 只把哈希 JSON URL 放进主包；进入页面时按需 fetch 当前语言与简中回退。不能移到固定 `public/locales` 地址，以免旧页面发布后拿到不兼容文案。
- 初始语言加载完成才挂载应用；失败显示小型本地化恢复入口。新工具进入前等待资源，已挂载工具切语时保留组件与状态。不要使用 `key={locale}` 或在切语期间移除工具。
- 选择语言先加载目标资源，成功后改变语言与 URL；失败保留当前页并可重试。fetch 的 10 秒期限也覆盖 JSON 读取。

## 展示 API

```ts
import { useAppTranslation, useMessages, msg, localizedName, localizePath } from "./i18n";
const { t, locale } = useAppTranslation("balloon");
const { render, tm } = useMessages();
// 状态保存引用；切语时重新显示，不保存固定译文。
const notice = msg("answer.sourceCode", { code: "WL-A1001" }, "balloon");
render(notice);
tm(rawApiIssue);
localizePath("/balloon", locale);
localizedName("characters", character.id, character.name);
```

`msg` 参数可嵌套另一条引用。原始 API/Worker 提示由 `messageTemplates.ts` 集中匹配；未知非中文提示使用本地化兜底，简中保留原文。业务筛选始终读取 raw issues，译文不参与推导、校验或指纹。

`names` 从同版本游戏表按原 ID 导入，只在 `/325` 使用；数值快照、媒体 ID 和 Worker 不包含语言数据。导入与长期背景见 [i18n-design.md](../../../docs/i18n-design.md)。

新增界面文案须同步四语键和插值，再运行 `npm run test:i18n`、`npm run test:calculator`、类型生成与生产构建。
