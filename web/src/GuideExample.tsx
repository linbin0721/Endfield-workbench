/** Annotated screenshot-scope example built on the committed, desensitized guide image. */
type Region = { key: string; marker: string; label: string; left: number; top: number; width: number; height: number };

// Percentages measured on web/public/balloon-screenshot-guide.png (1672×941).
const REGIONS: Region[] = [
  { key: "board", marker: "1", label: "完整棋盘与上方目标总升力", left: 37.68, top: 26.04, width: 24.82, height: 49.63 },
  { key: "inventory", marker: "2", label: "右侧完整库存", left: 76.85, top: 27.84, width: 21.53, height: 39.11 },
  { key: "code", marker: "3", label: "题号区域（可选）", left: 3.47, top: 27.84, width: 8.79, height: 6.16 },
];

// The target counter sits inside the board region, above the grid.
const TARGET = { left: 29.4, top: 1.5, width: 35.7, height: 8.6 };

export default function GuideExample() {
  return <section className="panel" aria-labelledby="guide-title">
    <div className="section-heading"><div><span className="eyebrow">00 / 示例</span><h2 id="guide-title">截图范围示例</h2></div>
      <span className="badge">已脱敏公开图</span></div>
    <p className="muted">截取游戏画面时请保留 1 号完整棋盘（含上方目标总升力）和 2 号全部库存；3 号题号可选，
      识别成功后用于题号目录的记录与复用。</p>
    <figure className="guide-figure">
      <div className="guide-frame">
        <img src={`${import.meta.env.BASE_URL}balloon-screenshot-guide.png`} loading="lazy"
          alt="截图范围示例：标出完整棋盘与目标总升力、完整库存，以及可选题号区域" />
        {REGIONS.map((region) => <span key={region.key} className={`guide-box guide-${region.key}`}
          style={{ left: `${region.left}%`, top: `${region.top}%`, width: `${region.width}%`, height: `${region.height}%` }}>
          <b className="guide-marker" aria-hidden="true">{region.marker}</b>
          {region.key === "board" && <span className="guide-target" style={{
            left: `${TARGET.left}%`, top: `${TARGET.top}%`, width: `${TARGET.width}%`, height: `${TARGET.height}%` }} />}
        </span>)}
      </div>
      <figcaption>
        <span><b>1</b> 必需：完整棋盘 + 目标总升力（示例 0/11）</span>
        <span><b>2</b> 必需：全部库存的等级、升力与数量</span>
        <span><b>3</b> 可选：题号 <code>WL-A</code> 加四位数字</span>
      </figcaption>
    </figure>
  </section>;
}
