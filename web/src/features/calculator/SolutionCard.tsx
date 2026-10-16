import EntityIcon from "../../calculator/EntityIcon.tsx";
import { ATTRIBUTE_NAMES, type Character, type Evaluation, type Solution } from "../../calculator/types.ts";
import { useAppTranslation, useMessages } from "../../i18n";
import { Button } from "../../ui/Button/Button";
import { ChevronDownIcon } from "../../ui/icons";
import {
  TARGET,
  activeSetLabels,
  attributeName,
  characterDisplayName,
  equipmentDisplayName,
  equipmentSetName,
  formatCount,
  formatValue,
  gemAttributeName,
  matchedSet,
  modifierLabel,
  modifierRefinement,
  modifierValue,
  orderEquipment,
  readVector,
  slotLabel,
  weaponById,
  weaponDisplayName,
  type CopyNotice,
} from "./model";
import s from "./calculator.module.css";

function AttributeGrid({ evaluation }: { evaluation: Evaluation }) {
  const { t } = useAppTranslation("calculator");
  const matched = matchedSet(evaluation);
  return <div className={s.attributes}>
    {ATTRIBUTE_NAMES.map((name, index) => {
      const value = readVector(evaluation.display, index);
      const reached = matched.has(index);
      const gap = value === null ? null : TARGET - value;
      const state = reached ? t("attributeState.reached", { target: TARGET })
        : gap === null ? t("attributeState.missing")
          : gap > 0 ? t("attributeState.gap", { gap: formatValue(gap) })
            : t("attributeState.above", { target: TARGET });
      return <div className={s.attribute} data-matched={reached} key={name}>
        <span className={s.attributeName}>{attributeName(index, t)}</span>
        <strong className={s.attributeValue}>{formatValue(value)}</strong>
        <span className={s.attributeState}>{state}</span>
      </div>;
    })}
  </div>;
}

/**
 * One build. The header toggles the details; the copy button sits in the
 * header so a collapsed build can still be copied.
 */
export function SolutionCard({ solution, index, character, expanded, copyNotice, onToggle, onCopy }: {
  solution: Solution;
  index: number;
  character: Character;
  expanded: boolean;
  copyNotice: CopyNotice;
  onToggle: () => void;
  onCopy: () => void;
}) {
  const { t } = useAppTranslation("calculator");
  const { render } = useMessages();
  const { build, evaluation } = solution;
  const matched = matchedSet(evaluation);
  const { names: setNames, unknown: unknownSets } = activeSetLabels(evaluation.activeSets);
  const weapon = weaponById.get(build.weapon?.id ?? "");
  const gemAttribute = gemAttributeName(weapon, character, t);
  const entries = orderEquipment(Array.isArray(build.equipment) ? build.equipment : []);
  const notice = copyNotice && copyNotice.solutionIndex === index ? copyNotice : null;
  const bodyId = `calc-solution-${index}-body`;
  return <article className={s.card} data-expanded={expanded} aria-labelledby={`calc-solution-${index}`}>
    <header className={s.cardHead}>
      <h3 className={s.cardHeading}>
        <button type="button" className={s.toggle} aria-expanded={expanded} aria-controls={bodyId} onClick={onToggle}>
          <EntityIcon kind="characters" id={character.id} name={characterDisplayName(character)} size={56} />
          <span className={s.toggleText}>
            <span id={`calc-solution-${index}`} className={s.cardTitle}>{t("solution.title", { index: index + 1, name: characterDisplayName(character) })}</span>
            <span className={s.cardMeta}>{t("solution.meta", { level: formatCount(build.level), potential: formatCount(build.potential) })}</span>
          </span>
          <ChevronDownIcon className={s.chevron} />
        </button>
      </h3>
      <span className={s.badge} data-reached={matched.size > 0}>{t("solution.badge", { count: matched.size })}</span>
      <div className={s.copyRow}>
        <Button variant="secondary" size="sm" onClick={onCopy}>{t("solution.copy")}</Button>
        {notice && <span className={s.copyStatus} data-ok={notice.ok} role="status" aria-live="polite">
          {render(notice.message, "error")}
        </span>}
      </div>
    </header>
    {expanded && <div className={s.body} id={bodyId}>
      <AttributeGrid evaluation={evaluation} />
      {(setNames.length > 0 || unknownSets > 0) && <p className={s.sets}>{t("solution.sets")}{setNames.map((name, position) =>
        <span className={s.setName} key={`${name}-${position}`}>{name}</span>)}
        {unknownSets > 0 && <span className={s.setName}>{t("solution.unknownSets", { count: unknownSets })}</span>}</p>}
      <div className={s.gear}>
        <section className={s.block} aria-label={t("solution.weaponSection")}>
          <h4 className={s.blockTitle}>{t("solution.weaponSection")}</h4>
          <div className={s.entity}>
            <EntityIcon kind="weapons" id={build.weapon?.id ?? ""} name={weaponDisplayName(weapon, t)} rarity={weapon?.rarity} />
            <div className={s.entityText}>
              <p><strong>{weaponDisplayName(weapon, t)}</strong></p>
              {weapon && <p className={s.muted}>{t("solution.weaponLevel", { level: formatCount(weapon.level) })}</p>}
              {!weapon && <p className={s.missing}>{t("solution.weaponMissing")}</p>}
            </div>
          </div>
          <ul className={s.tags}>
            <li>{t("solution.refine", { value: formatCount(build.weapon?.refinement) })}</li>
            <li>{t("solution.gemFirst", { attribute: gemAttribute ? t("copy.gemAttribute", { attribute: gemAttribute }) : "",
              value: formatCount(build.weapon?.gemFirst) })}</li>
            <li>{t("solution.gemPassive", { value: formatCount(build.weapon?.gemPassive) })}</li>
          </ul>
          <p className={s.muted}>{t("solution.gemNote")}</p>
        </section>
        <section className={s.block} aria-label={t("solution.gearSection")}>
          <h4 className={s.blockTitle}>{t("solution.gearSection")}</h4>
          <div className={s.equipList}>
            {entries.map((entry, position) => {
              const setName = equipmentSetName(entry.item);
              return <div className={s.equip} key={`${entry.gear.id}-${position}`}>
                <div className={s.entity}>
                  {entry.gear.id && <EntityIcon kind="equipment" id={entry.gear.id}
                    name={equipmentDisplayName(entry.gear, entry.item, t)} size={56} />}
                  <div className={s.entityText}>
                    <span className={s.slot}>{slotLabel(entry, t)}</span>
                    <p><strong>{equipmentDisplayName(entry.gear, entry.item, t)}</strong></p>
                    {entry.gear.id && setName && <p className={s.muted}>{t("solution.set", { name: setName })}</p>}
                    {entry.gear.id && !entry.item && <p className={s.missing}>{t("solution.gearMissing")}</p>}
                  </div>
                </div>
                {entry.gear.id && (entry.item
                  ? <ul className={s.mods}>{entry.item.modifiers.map((modifier, modifierPosition) => {
                    const refinement = modifierRefinement(entry.gear, modifierPosition);
                    return <li className={s.mod} key={`${modifier.index}-${modifier.scope}-${modifier.attribute}-${modifierPosition}`}>
                      <span>{t("solution.modifier", { refinement, label: modifierLabel(modifier, character, t) })}</span>
                      <b>{modifierValue(modifier, refinement)}</b>
                    </li>;
                  })}</ul>
                  : <p className={s.muted}>{t("solution.modsUnavailable")}</p>)}
              </div>;
            })}
          </div>
        </section>
      </div>
    </div>}
  </article>;
}
