import { useAppTranslation } from "./i18n";

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
  const { t } = useAppTranslation("balloon");
  return <section className="panel" aria-labelledby="code-guide-title">
    <div className="section-heading"><div><span className="eyebrow">{t("examples.eyebrow")}</span><h2 id="code-guide-title">{t("examples.codeTitle")}</h2></div>
      <span className="badge">{t("examples.scopeBadge")}</span></div>
    <p className="muted">{t("examples.codeIntro")}</p>
    <figure className="guide-figure">
      <div className="guide-frame">
        <img src={`${import.meta.env.BASE_URL}balloon-screenshot-guide.png`} loading="lazy"
          alt={t("examples.codeAlt")} />
        <span className="guide-box guide-code guide-code-only" style={{
          left: `${CODE_REGION.left}%`, top: `${CODE_REGION.top}%`,
          width: `${CODE_REGION.width}%`, height: `${CODE_REGION.height}%` }}>
          <b className="guide-marker guide-marker-outside" aria-hidden="true">{t("examples.codeMarker")}</b>
        </span>
      </div>
      <figcaption><span>{t("examples.codeCaption")}</span></figcaption>
    </figure>
  </section>;
}
