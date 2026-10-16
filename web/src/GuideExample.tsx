import { SectionHead, cx } from "./features/puzzles/PuzzleParts";
import s from "./features/puzzles/puzzles.module.css";
import { useAppTranslation } from "./i18n";
import { Panel } from "./ui/Panel/Panel";

/** Annotated screenshot-scope example built on the committed, desensitized guide image. */
type Region = { key: string; marker: string; left: number; top: number; width: number; height: number; outside?: boolean };

// Percentages measured on web/public/balloon-screenshot-guide.png (1672×941).
// The code marker sits outside its box so no guide marker can cover the printed question number.
const REGIONS: Region[] = [
  { key: "board", marker: "1", left: 37.68, top: 26.04, width: 24.82, height: 49.63 },
  { key: "inventory", marker: "2", left: 76.85, top: 27.84, width: 21.53, height: 39.11 },
  { key: "code", marker: "3", left: 3.47, top: 27.84, width: 8.79, height: 6.16, outside: true },
];

const REGION_CLASS: Record<string, string> = { board: s.guideBoard, inventory: s.guideInventory, code: s.guideCode };

// The target counter sits inside the board region, above the grid.
const TARGET = { left: 29.4, top: 1.5, width: 35.7, height: 8.6 };

export default function GuideExample() {
  const { t } = useAppTranslation("balloon");
  return <Panel as="section" aria-labelledby="guide-title">
    <SectionHead eyebrow={t("examples.eyebrow")} title={t("examples.scopeTitle")} id="guide-title" badge={t("examples.scopeBadge")} />
    <p className={s.text}>{t("examples.scopeIntro")}</p>
    <figure className={s.figure}>
      <div className={s.guideFrame}>
        <img className={s.guideImage} src={`${import.meta.env.BASE_URL}balloon-screenshot-guide.png`} loading="lazy"
          alt={t("examples.scopeAlt")} />
        {REGIONS.map((region) => <span key={region.key} className={cx(s.guideBox, REGION_CLASS[region.key])}
          style={{ left: `${region.left}%`, top: `${region.top}%`, width: `${region.width}%`, height: `${region.height}%` }}>
          <b className={cx(s.guideMarker, region.outside && s.guideMarkerOutside)} aria-hidden="true">{region.marker}</b>
          {region.key === "board" && <span className={s.guideTarget} style={{
            left: `${TARGET.left}%`, top: `${TARGET.top}%`, width: `${TARGET.width}%`, height: `${TARGET.height}%` }} />}
        </span>)}
      </div>
      <figcaption className={s.caption}>
        <span>{t("examples.scopeCaptionBoard")}</span>
        <span>{t("examples.scopeCaptionInventory")}</span>
        <span>{t("examples.scopeCaptionCode")}</span>
      </figcaption>
    </figure>
  </Panel>;
}
