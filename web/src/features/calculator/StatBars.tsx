import type { CSSProperties } from "react";
import { ATTRIBUTE_NAMES, type Evaluation } from "../../calculator/types.ts";
import { useAppTranslation } from "../../i18n";
import { SOURCE_KINDS, type AxisBreakdown } from "./breakdown";
import { TARGET, attributeName, formatValue, matchedSet, readVector } from "./model";
import b from "./bench.module.css";

const percentText = (value: number) => formatValue(value * 100);
/** Two decimals, truncated, so the integer part of raw always equals the floored panel value. */
const rawText = (value: number) => (Math.floor(value * 100) / 100).toFixed(2);

/**
 * The four panel values as bars against the 325 line. When the breakdown
 * reproduced the value exactly, the bar is split by source and the formula
 * is spelled out; otherwise only the total is drawn.
 */
export function StatBars({ evaluation, breakdown, required }: {
  evaluation: Evaluation;
  breakdown: (AxisBreakdown | null)[];
  required: readonly number[];
}) {
  const { t } = useAppTranslation("calculator");
  const matched = matchedSet(evaluation);
  const values = ATTRIBUTE_NAMES.map((_, axis) => readVector(evaluation.display, axis));
  const scale = Math.max(TARGET * 1.12, ...values.map((value) => value ?? 0));
  const width = (value: number) => `${Math.max(0, (value / scale) * 100)}%`;
  return <div className={b.stats}>
    <ul className={b.legend} aria-label={t("bench.legend")}>
      {SOURCE_KINDS.map((kind) => <li key={kind} data-source={kind}>{t(`bench.source.${kind}`)}</li>)}
    </ul>
    {values.map((value, axis) => {
      const parts = breakdown[axis];
      const reached = matched.has(axis);
      const gap = value === null ? null : TARGET - value;
      const state = reached ? t("attributeState.reached", { target: TARGET })
        : gap === null ? t("attributeState.missing")
          : gap > 0 ? t("attributeState.gap", { gap: formatValue(gap) })
            : t("attributeState.above", { target: TARGET });
      return <div key={axis} className={b.stat} data-matched={reached || undefined} data-breakdown={parts ? "exact" : "none"}>
        <div className={b.statHead}>
          <span className={b.statName}>
            {attributeName(axis, t)}
            {required.includes(axis) && <em className={b.required}>{t("bench.requiredTag")}</em>}
          </span>
          <strong className={b.statValue}>{formatValue(value)}</strong>
          <span className={b.statState}>{state}</span>
        </div>
        <div className={b.track} role="img" aria-label={t("bench.barLabel", { name: attributeName(axis, t), value: formatValue(value), target: TARGET })}
          style={{ "--target": width(TARGET) } as CSSProperties}>
          {parts
            ? parts.parts.map((part) => part.value > 0 &&
              <span key={part.kind} className={b.segment} data-source={part.kind} style={{ width: width(part.value) }} />)
            : value !== null && <span className={b.segment} data-source="total" style={{ width: width(value) }} />}
          <span className={b.targetLine} aria-hidden="true"><i>{TARGET}</i></span>
        </div>
        {parts && <p className={b.parts}>
          {parts.parts.filter((part) => part.flat !== 0 || part.percent !== 0).map((part) => <span key={part.kind} data-source={part.kind}>
            {t(`bench.source.${part.kind}`)} {formatValue(part.value)}
            {part.percent !== 0 && <small>{t("bench.partPercent", { value: percentText(part.percent) })}</small>}
          </span>)}
          <span className={b.formula}>{t("bench.formula", {
            flat: rawText(parts.flat), percent: percentText(parts.percent), raw: rawText(parts.raw), display: formatValue(value),
          })}</span>
        </p>}
      </div>;
    })}
  </div>;
}
