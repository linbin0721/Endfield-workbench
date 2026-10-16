import { useId } from "react";
import { circuitColorOnSurface } from "./features/puzzles/circuitTheme";
import { SectionHead, cx } from "./features/puzzles/PuzzleParts";
import s from "./features/puzzles/puzzles.module.css";
import { useAppTranslation } from "./i18n";
import { Panel } from "./ui/Panel/Panel";
import { useSurface } from "./ui/surface";
import {
  circuitColorStyle,
  circuitFallbackDisplayColor,
  circuitPieceBoundarySegments,
  circuitPieceFill,
  type CircuitDisplayColor,
  type CircuitDisplayPoint,
} from "./circuitDisplay";

type Props = { mode: "screenshot" | "code" };

const GUIDE_CELLS = [
  -1, 0, null, null,
  1, null, null, null,
  null, null, 0, null,
  null, null, null, null,
] as const;

const GUIDE_PIECES = [
  { channel: 0, cells: [{ row: 0, column: 0 }, { row: 1, column: 0 }] },
  { channel: 1, cells: [{ row: 0, column: 0 }, { row: 1, column: 0 }, { row: 1, column: 1 }] },
  { channel: 1, cells: [{ row: 0, column: 0 }] },
];
const GUIDE_COLORS = [circuitFallbackDisplayColor(0), circuitFallbackDisplayColor(1)];

function CircuitGuidePiece({ cells, color }: {
  cells: readonly CircuitDisplayPoint[];
  color: CircuitDisplayColor;
}) {
  const id = useId().replace(/:/g, "");
  const fill = circuitPieceFill(cells);
  const outline = circuitPieceBoundarySegments(cells).map((segment) =>
    `M${segment.x1} ${segment.y1}L${segment.x2} ${segment.y2}`).join("");
  const padding = 0.14;
  return <svg className={s.guidePieceSvg}
    viewBox={`${fill.bounds.x1 - padding} ${fill.bounds.y1 - padding} ${fill.bounds.x2 - fill.bounds.x1 + padding * 2} ${fill.bounds.y2 - fill.bounds.y1 + padding * 2}`}
    aria-hidden="true">
    <defs>
      <linearGradient id={`${id}-fill`} gradientUnits="userSpaceOnUse"
        x1={fill.bounds.x1} y1={fill.bounds.y1} x2={fill.bounds.x2} y2={fill.bounds.y2}>
        <stop offset="0" stopColor={color.highlight} />
        <stop offset="0.24" stopColor={color.fill} />
        <stop offset="1" stopColor={color.softFill} />
      </linearGradient>
    </defs>
    <path d={fill.pathData} fill={`url(#${id}-fill)`} data-circuit-guide-piece-fill="" />
    <path d={outline} fill="none" stroke={color.edge} strokeWidth="0.095"
      strokeLinejoin="round" strokeLinecap="round" />
    <path d={outline} fill="none" stroke={color.highlight} strokeWidth="0.025"
      strokeLinejoin="round" strokeLinecap="round" opacity="0.72" />
  </svg>;
}

export default function CircuitGuideExample({ mode }: Props) {
  const { t } = useAppTranslation("circuit");
  const surface = useSurface();
  const colors = GUIDE_COLORS.map((color) => circuitColorOnSurface(color, surface));
  const titleId = `circuit-guide-${mode}-title`;
  const screenshot = mode === "screenshot";
  return <Panel as="section" aria-labelledby={titleId}>
    <SectionHead eyebrow={t("examples.eyebrow")} title={screenshot ? t("examples.screenshotTitle") : t("examples.codeTitle")}
      id={titleId} badge={t("examples.badge")} />
    <p className={s.text}>{screenshot ? t("examples.screenshotIntro") : t("examples.codeIntro")}</p>
    <figure className={cx(s.figure, s.circuitGuide)} aria-label={t("examples.figureAria")}>
      <div className={cx(s.guideRegion, s.guideCode, s.guideCodeRegion)}>
        <b className={s.guideMarker} aria-hidden="true">3</b>
        <code>△-V40020</code>
      </div>
      <div className={cx(s.guideRegion, s.guideBoard, s.guideBoardRegion)}>
        <b className={s.guideMarker} aria-hidden="true">1</b>
        <div className={s.guideBoardGrid}>
          {GUIDE_CELLS.map((channel, index) => {
            const color = channel != null && channel >= 0 ? colors[channel] : null;
            const kind = channel === -1 ? "blocked" : color ? "fixed" : "empty";
            return <span key={index} className={cx(s.circuitCell, color && s.pattern)} data-cell={kind}
              style={color ? circuitColorStyle(color) : undefined} data-circuit-pattern={color?.channel}>
              {channel === -1 ? <i className={s.obstacleMark} aria-hidden="true" />
                : color ? <i className={s.fixedMark} aria-hidden="true" /> : null}
            </span>;
          })}
        </div>
      </div>
      <div className={cx(s.guideRegion, s.guideInventory, s.guidePieces)}>
        <b className={s.guideMarker} aria-hidden="true">2</b>
        {GUIDE_PIECES.map((piece, index) => <div className={s.guidePiece} key={index}>
          <CircuitGuidePiece cells={piece.cells} color={colors[piece.channel]} />
        </div>)}
      </div>
    </figure>
  </Panel>;
}
