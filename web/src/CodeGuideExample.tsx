import { SectionHead } from "./features/puzzles/PuzzleParts";
import s from "./features/puzzles/puzzles.module.css";
import { useAppTranslation } from "./i18n";
import { Panel } from "./ui/Panel/Panel";

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
  return <Panel as="section" aria-labelledby="code-guide-title">
    <SectionHead eyebrow={t("examples.eyebrow")} title={t("examples.codeTitle")} id="code-guide-title" badge={t("examples.scopeBadge")} />
    <p className={s.text}>{t("examples.codeIntro")}</p>
    <figure className={s.figure}>
      <div className={s.guideFrame}>
        <img className={s.guideImage} src={`${import.meta.env.BASE_URL}balloon-screenshot-guide.png`} loading="lazy"
          alt={t("examples.codeAlt")} />
        <span className={`${s.guideBox} ${s.guideCode} ${s.guideCodeOnly}`} style={{
          left: `${CODE_REGION.left}%`, top: `${CODE_REGION.top}%`,
          width: `${CODE_REGION.width}%`, height: `${CODE_REGION.height}%` }}>
          <b className={`${s.guideMarker} ${s.guideMarkerOutside}`} aria-hidden="true">{t("examples.codeMarker")}</b>
        </span>
      </div>
      <figcaption className={s.caption}><span>{t("examples.codeCaption")}</span></figcaption>
    </figure>
  </Panel>;
}
