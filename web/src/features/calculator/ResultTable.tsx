import EntityIcon from "../../calculator/EntityIcon.tsx";
import { ATTRIBUTE_NAMES, type Solution } from "../../calculator/types.ts";
import { useAppTranslation } from "../../i18n";
import { ATTRIBUTE_KEYS, attributeName, formatValue, matchedSet, readVector, weaponById, weaponDisplayName } from "./model";
import b from "./bench.module.css";

/**
 * All builds side by side: the four panel values (325 highlighted), how many
 * reached it and the weapon. Choosing a row shows that build on the bench.
 */
export function ResultTable({ results, selected, onSelect }: {
  results: Solution[];
  selected: number;
  onSelect: (index: number) => void;
}) {
  const { t } = useAppTranslation("calculator");
  return <div className={b.tableWrap}>
    <table className={b.table}>
      <caption className={b.caption}>{t("bench.tableCaption")}</caption>
      <thead>
        <tr>
          <th scope="col">{t("bench.colBuild")}</th>
          {ATTRIBUTE_NAMES.map((_, axis) => <th scope="col" key={axis} className={b.num}>
            <span className={b.full}>{attributeName(axis, t)}</span>
            <abbr className={b.short} title={attributeName(axis, t)}>{t(`bench.short.${ATTRIBUTE_KEYS[axis]}`)}</abbr>
          </th>)}
          <th scope="col" className={b.num}>{t("bench.colMatched")}</th>
          <th scope="col" className={b.weaponCol}>{t("bench.colWeapon")}</th>
        </tr>
      </thead>
      <tbody>
        {results.map((solution, index) => {
          const matched = matchedSet(solution.evaluation);
          const weapon = weaponById.get(solution.build.weapon?.id ?? "");
          const name = weaponDisplayName(weapon, t);
          return <tr key={index} data-selected={index === selected || undefined} onClick={() => onSelect(index)}>
            <th scope="row">
              <button type="button" className={b.rowButton} aria-pressed={index === selected}
                aria-label={t("bench.selectBuild", { index: index + 1 })} onClick={(event) => { event.stopPropagation(); onSelect(index); }}>
                {String(index + 1).padStart(2, "0")}
              </button>
            </th>
            {ATTRIBUTE_NAMES.map((_, axis) => <td key={axis} className={b.num} data-matched={matched.has(axis) || undefined}>
              {formatValue(readVector(solution.evaluation.display, axis))}
            </td>)}
            <td className={b.num}><span className={b.count} data-reached={matched.size > 0 || undefined}>{matched.size}</span></td>
            <td className={b.weaponCol}>
              <span className={b.weaponCell}>
                <EntityIcon kind="weapons" id={solution.build.weapon?.id ?? ""} name={name} rarity={weapon?.rarity} size={56} />
                <span>{name}</span>
              </span>
            </td>
          </tr>;
        })}
      </tbody>
    </table>
  </div>;
}
