import { useAppTranslation } from "../../i18n";
import w from "../workbench/workbench.module.css";
import s from "./balloon.module.css";

type Region = { key: "board" | "inventory" | "code"; marker: string; left: number; top: number; width: number; height: number; outside?: boolean };

// Percentages measured on web/public/balloon-screenshot-guide.png (1672×941).
// The code marker sits outside its box so no marker covers the printed question number.
const REGIONS: Region[] = [
  { key: "board", marker: "1", left: 37.68, top: 26.04, width: 24.82, height: 49.63 },
  { key: "inventory", marker: "2", left: 76.85, top: 27.84, width: 21.53, height: 39.11 },
  { key: "code", marker: "3", left: 3.47, top: 27.84, width: 8.79, height: 6.16, outside: true },
];
// The target counter sits inside the board region, above the grid.
const TARGET = { left: 29.4, top: 1.5, width: 35.7, height: 8.6 };
const IMAGE = `${import.meta.env.BASE_URL}balloon-screenshot-guide.png`;

/** Help panel content: what to capture, where the question code is, and the upload notes. */
export function BalloonHelp() {
  const { t } = useAppTranslation("balloon");
  const { t: tc } = useAppTranslation("common");
  return <div className={w.help}>
    <section className={w.helpSection} aria-labelledby="balloon-help-scope">
      <h3 id="balloon-help-scope" className={w.helpTitle}>{t("examples.scopeTitle")}</h3>
      <p className={w.helpText}>{t("examples.scopeIntro")}</p>
      <figure className={s.figure}>
        <div className={s.guide}>
          <img src={IMAGE} loading="lazy" alt={t("examples.scopeAlt")} />
          {REGIONS.map((region) => <span key={region.key} className={s.guideBox} data-region={region.key}
            style={{ left: `${region.left}%`, top: `${region.top}%`, width: `${region.width}%`, height: `${region.height}%` }}>
            <b className={s.marker} data-outside={region.outside || undefined} aria-hidden="true">{region.marker}</b>
            {region.key === "board" && <span className={s.guideTarget} style={{
              left: `${TARGET.left}%`, top: `${TARGET.top}%`, width: `${TARGET.width}%`, height: `${TARGET.height}%` }} />}
          </span>)}
        </div>
        <figcaption className={s.helpCaption}>
          <span>{t("examples.scopeCaptionBoard")}</span>
          <span>{t("examples.scopeCaptionInventory")}</span>
          <span>{t("examples.scopeCaptionCode")}</span>
        </figcaption>
      </figure>
    </section>
    <section className={w.helpSection} aria-labelledby="balloon-help-code">
      <h3 id="balloon-help-code" className={w.helpTitle}>{t("examples.codeTitle")}</h3>
      <p className={w.helpText}>{t("examples.codeIntro")}</p>
    </section>
    <section className={w.helpSection} aria-labelledby="balloon-help-notes">
      <h3 id="balloon-help-notes" className={w.helpTitle}>{tc("workbench.notesTitle")}</h3>
      <ul className={w.helpList}>
        <li>{tc("image.ocrNote")}</li>
        <li>{tc("image.limits")}</li>
        <li>{t("recognize.description")}</li>
      </ul>
    </section>
  </div>;
}
