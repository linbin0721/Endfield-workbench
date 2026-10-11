import { useAppTranslation } from "./i18n";

/** Annotated screenshot-scope example built on the committed, desensitized guide image. */
type Region = { key: string; marker: string; left: number; top: number; width: number; height: number; outside?: boolean };

// Percentages measured on web/public/balloon-screenshot-guide.png (1672×941).
// The code marker sits outside its box so no guide marker can cover the printed question number.
const REGIONS: Region[] = [
  { key: "board", marker: "1", left: 37.68, top: 26.04, width: 24.82, height: 49.63 },
  { key: "inventory", marker: "2", left: 76.85, top: 27.84, width: 21.53, height: 39.11 },
  { key: "code", marker: "3", left: 3.47, top: 27.84, width: 8.79, height: 6.16, outside: true },
];

// The target counter sits inside the board region, above the grid.
const TARGET = { left: 29.4, top: 1.5, width: 35.7, height: 8.6 };

export default function GuideExample() {
  const { t } = useAppTranslation("balloon");
  return <section className="panel" aria-labelledby="guide-title">
    <div className="section-heading"><div><span className="eyebrow">{t("examples.eyebrow")}</span><h2 id="guide-title">{t("examples.scopeTitle")}</h2></div>
      <span className="badge">{t("examples.scopeBadge")}</span></div>
    <p className="muted">{t("examples.scopeIntro")}</p>
    <figure className="guide-figure">
      <div className="guide-frame">
        <img src={`${import.meta.env.BASE_URL}balloon-screenshot-guide.png`} loading="lazy"
          alt={t("examples.scopeAlt")} />
        {REGIONS.map((region) => <span key={region.key} className={`guide-box guide-${region.key}`}
          style={{ left: `${region.left}%`, top: `${region.top}%`, width: `${region.width}%`, height: `${region.height}%` }}>
          <b className={`guide-marker${region.outside ? " guide-marker-outside" : ""}`} aria-hidden="true">{region.marker}</b>
          {region.key === "board" && <span className="guide-target" style={{
            left: `${TARGET.left}%`, top: `${TARGET.top}%`, width: `${TARGET.width}%`, height: `${TARGET.height}%` }} />}
        </span>)}
      </div>
      <figcaption>
        <span>{t("examples.scopeCaptionBoard")}</span>
        <span>{t("examples.scopeCaptionInventory")}</span>
        <span>{t("examples.scopeCaptionCode")}</span>
      </figcaption>
    </figure>
  </section>;
}
