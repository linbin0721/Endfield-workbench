/**
 * Question-number example for the "query by code" entry: the same committed,
 * desensitized guide image as GuideExample, annotated only where the code sits.
 */
// Percentages measured on web/public/balloon-screenshot-guide.png (1672×941).
// The printed code (icon + "WL-A1001") spans x 47–186, y 262–286; this box adds a
// small margin and stops above the separator bar at y≈307. The label is rendered
// outside the box, so no guide element can cover the printed question number.
const CODE_REGION = { left: 1.8, top: 26.4, width: 10.8, height: 5.8 };

export default function CodeGuideExample() {
  return <section className="panel" aria-labelledby="code-guide-title">
    <div className="section-heading"><div><span className="eyebrow">00 / 示例</span><h2 id="code-guide-title">题号位置示例</h2></div>
      <span className="badge">已脱敏公开图</span></div>
    <p className="muted">题号印在画面左侧、棋盘之外，格式为 <code>WL-A</code> 加四位数字（示例 <code>WL-A1001</code>）。
      按题号查询只读取这一处文字，不需要上传图片。</p>
    <figure className="guide-figure">
      <div className="guide-frame">
        <img src={`${import.meta.env.BASE_URL}balloon-screenshot-guide.png`} loading="lazy"
          alt="题号位置示例：在画面左侧棋盘外标出题号 WL-A 加四位数字的位置" />
        <span className="guide-box guide-code guide-code-only" style={{
          left: `${CODE_REGION.left}%`, top: `${CODE_REGION.top}%`,
          width: `${CODE_REGION.width}%`, height: `${CODE_REGION.height}%` }}>
          <b className="guide-marker guide-marker-outside" aria-hidden="true">题号</b>
        </span>
      </div>
      <figcaption><span>只标注题号位置：<code>WL-A</code> 加四位数字（示例 <code>WL-A1001</code>）</span></figcaption>
    </figure>
  </section>;
}
