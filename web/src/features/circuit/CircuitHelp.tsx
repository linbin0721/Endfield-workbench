import { useAppTranslation } from "../../i18n";
import { circuitFallbackDisplayColor } from "../../circuitDisplay";
import { useSurface } from "../../ui/surface";
import w from "../workbench/workbench.module.css";
import { CircuitBoard } from "./CircuitBoard";
import { circuitColorOnSurface } from "./circuitTheme";
import { PieceShape } from "./CircuitPieces";
import type { CircuitDraft } from "./draft";
import c from "./circuit.module.css";

// A small made-up puzzle (not a game screenshot): 4×4 board, two channels.
const GUIDE: CircuitDraft = {
  rows: 4,
  columns: 4,
  channels: [
    { index: 0, row_targets: [1, 0, 1, 0], column_targets: [1, 1, 0, 0] },
    { index: 1, row_targets: [0, 1, 1, 2], column_targets: [1, 0, 2, 1] },
  ],
  cells: [
    "blocked", "fixed0", "empty", "empty",
    "fixed1", "empty", "empty", "empty",
    "empty", "empty", "fixed0", "empty",
    "empty", "empty", "empty", "empty",
  ].map((kind) => kind.startsWith("fixed")
    ? { kind: "fixed" as const, channel: Number(kind.slice(5)) }
    : { kind: kind as "empty" | "blocked", channel: null }),
  pieces: [
    { channel: 0, cells: [{ row: 0, column: 0 }, { row: 1, column: 0 }] },
    { channel: 1, cells: [{ row: 0, column: 0 }, { row: 1, column: 0 }, { row: 1, column: 1 }] },
    { channel: 1, cells: [{ row: 0, column: 0 }] },
  ],
  palette: null,
};

/** Help panel content: what to capture, where the code is, and how editing works. */
export function CircuitHelp() {
  const { t } = useAppTranslation("circuit");
  const { t: tc } = useAppTranslation("common");
  const surface = useSurface();
  const colors = [0, 1].map((channel) => circuitColorOnSurface(circuitFallbackDisplayColor(channel), surface));
  return <div className={w.help}>
    <section className={w.helpSection} aria-labelledby="circuit-help-scope">
      <h3 id="circuit-help-scope" className={w.helpTitle}>{t("examples.screenshotTitle")}</h3>
      <p className={w.helpText}>{t("examples.screenshotIntro")}</p>
      <figure className={c.guide} aria-label={t("examples.figureAria")}>
        <div className={c.guideRegion} data-region="code"><b>3</b><code>△-V40020</code></div>
        <div className={c.guideRegion} data-region="board"><b>1</b>
          <CircuitBoard draft={GUIDE} colors={colors} mode="view" size="sm" />
        </div>
        <div className={c.guideRegion} data-region="inventory"><b>2</b>
          <div className={c.guidePieces}>
            {GUIDE.pieces.map((piece, index) => <PieceShape key={index} cells={piece.cells} color={colors[piece.channel]} />)}
          </div>
        </div>
      </figure>
    </section>
    <section className={w.helpSection} aria-labelledby="circuit-help-code">
      <h3 id="circuit-help-code" className={w.helpTitle}>{t("examples.codeTitle")}</h3>
      <p className={w.helpText}>{t("examples.codeIntro")}</p>
    </section>
    <section className={w.helpSection} aria-labelledby="circuit-help-edit">
      <h3 id="circuit-help-edit" className={w.helpTitle}>{t("workbench.helpEditTitle")}</h3>
      <ul className={w.helpList}>
        <li>{t("workbench.helpEditTargets")}</li>
        <li>{t("workbench.helpEditCells")}</li>
        <li>{t("workbench.helpEditPieces")}</li>
      </ul>
    </section>
    <section className={w.helpSection} aria-labelledby="circuit-help-notes">
      <h3 id="circuit-help-notes" className={w.helpTitle}>{tc("workbench.notesTitle")}</h3>
      <ul className={w.helpList}>
        <li>{tc("image.ocrNote")}</li>
        <li>{tc("image.limits")}</li>
        <li>{t("recognize.description")}</li>
      </ul>
    </section>
  </div>;
}
