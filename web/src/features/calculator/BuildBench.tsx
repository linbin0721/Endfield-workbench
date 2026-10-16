import { useMemo } from "react";
import { gameData } from "../../calculator/data.ts";
import EntityIcon from "../../calculator/EntityIcon.tsx";
import type { Character, Solution } from "../../calculator/types.ts";
import { useAppTranslation, useMessages } from "../../i18n";
import { Button } from "../../ui/Button/Button";
import { breakdownBuild } from "./breakdown";
import {
  activeSetLabels,
  characterDisplayName,
  equipmentDisplayName,
  equipmentSetName,
  formatCount,
  gemAttributeName,
  modifierLabel,
  modifierRefinement,
  modifierValue,
  orderEquipment,
  slotLabel,
  weaponById,
  weaponDisplayName,
  type CopyNotice,
  type EquipmentEntry,
} from "./model";
import { StatBars } from "./StatBars";
import b from "./bench.module.css";

/** Filled / empty pips for a level out of `max`. */
function Pips({ value, max, label }: { value: number; max: number; label: string }) {
  return <span className={b.pips} role="img" aria-label={label}>
    {Array.from({ length: max }, (_, index) => <i key={index} data-on={index < value || undefined} />)}
  </span>;
}

function GearSlot({ entry, character }: { entry: EquipmentEntry; character: Character }) {
  const { t } = useAppTranslation("calculator");
  const name = equipmentDisplayName(entry.gear, entry.item, t);
  const setName = equipmentSetName(entry.item);
  return <section className={b.slot} data-empty={!entry.gear.id || undefined} aria-label={`${slotLabel(entry, t)} · ${name}`}>
    <header className={b.slotHead}>
      {entry.gear.id ? <EntityIcon kind="equipment" id={entry.gear.id} name={name} /> : <span className={b.slotEmpty} aria-hidden="true" />}
      <div className={b.slotText}>
        <span className={b.slotLabel}>{slotLabel(entry, t)}</span>
        <strong className={b.slotName}>{name}</strong>
        {entry.gear.id && setName && <span className={b.slotSet}>{setName}</span>}
        {entry.gear.id && !entry.item && <span className={b.missing}>{t("solution.gearMissing")}</span>}
      </div>
    </header>
    {entry.gear.id && entry.item && <ul className={b.mods}>
      {entry.item.modifiers.map((modifier, position) => {
        const refinement = modifierRefinement(entry.gear, position);
        const max = Math.min(3, Math.max(0, modifier.values.length - 1));
        return <li key={`${modifier.index}-${modifier.scope}-${modifier.attribute}-${position}`} className={b.mod}>
          <span className={b.modName}>{modifierLabel(modifier, character, t)}</span>
          <b className={b.modValue}>{modifierValue(modifier, refinement)}</b>
          {max > 0 && <Pips value={refinement} max={max} label={t("bench.refineLevel", { value: refinement, max })} />}
        </li>;
      })}
    </ul>}
  </section>;
}

/**
 * The loadout of one build: operator, weapon with its gem affixes, the four
 * gear slots with their refinement levels, active sets and the panel bars.
 */
export function BuildBench({ solution, index, character, required, copyNotice, onCopy }: {
  solution: Solution;
  index: number;
  character: Character;
  required: readonly number[];
  copyNotice: CopyNotice;
  onCopy: () => void;
}) {
  const { t } = useAppTranslation("calculator");
  const { render } = useMessages();
  const { build, evaluation } = solution;
  const weapon = weaponById.get(build.weapon?.id ?? "");
  const weaponName = weaponDisplayName(weapon, t);
  const gemAttribute = gemAttributeName(weapon, character, t);
  const entries = orderEquipment(Array.isArray(build.equipment) ? build.equipment : []);
  const { names: setNames, unknown: unknownSets } = activeSetLabels(evaluation.activeSets);
  const breakdown = useMemo(() => breakdownBuild(gameData, build, evaluation), [build, evaluation]);
  const notice = copyNotice && copyNotice.solutionIndex === index ? copyNotice : null;
  const name = characterDisplayName(character);
  return <article className={b.bench} aria-labelledby="calc-bench-title" data-bench={index}>
    <header className={b.benchHead}>
      <EntityIcon kind="characters" id={character.id} name={name} size={88} />
      <div className={b.benchTitle}>
        <span className={b.benchIndex}>{t("bench.buildIndex", { index: index + 1 })}</span>
        <h3 id="calc-bench-title" className={b.benchName}>{name}</h3>
        <span className={b.benchMeta}>{t("solution.meta", { level: formatCount(build.level), potential: formatCount(build.potential) })}</span>
      </div>
      <div className={b.copy}>
        <Button variant="secondary" size="sm" onClick={onCopy}>{t("solution.copy")}</Button>
        {notice && <span className={b.copyStatus} data-ok={notice.ok} role="status" aria-live="polite">{render(notice.message, "error")}</span>}
      </div>
    </header>

    <div className={b.loadout}>
      <section className={b.weapon} aria-label={t("solution.weaponSection")}>
        <header className={b.slotHead}>
          <EntityIcon kind="weapons" id={build.weapon?.id ?? ""} name={weaponName} rarity={weapon?.rarity} size={88} />
          <div className={b.slotText}>
            <span className={b.slotLabel}>{t("bench.weaponSlot")}</span>
            <strong className={b.slotName}>{weaponName}</strong>
            {weapon && <span className={b.slotSet}>{t("solution.weaponLevel", { level: formatCount(weapon.level) })}</span>}
            {!weapon && <span className={b.missing}>{t("solution.weaponMissing")}</span>}
          </div>
        </header>
        <ul className={b.mods}>
          <li className={b.mod}>
            <span className={b.modName}>{t("bench.refine")}</span>
            <b className={b.modValue}>+{formatCount(build.weapon?.refinement)}</b>
            <Pips value={build.weapon?.refinement ?? 0} max={5} label={t("bench.refineLevel", { value: build.weapon?.refinement ?? 0, max: 5 })} />
          </li>
          <li className={b.mod}>
            <span className={b.modName}>{t("bench.gemFirst", { attribute: gemAttribute ? t("copy.gemAttribute", { attribute: gemAttribute }) : "" })}</span>
            <b className={b.modValue}>+{formatCount(build.weapon?.gemFirst)}</b>
            <Pips value={build.weapon?.gemFirst ?? 0} max={6} label={t("bench.refineLevel", { value: build.weapon?.gemFirst ?? 0, max: 6 })} />
          </li>
          <li className={b.mod}>
            <span className={b.modName}>{t("bench.gemPassive")}</span>
            <b className={b.modValue}>+{formatCount(build.weapon?.gemPassive)}</b>
            <Pips value={build.weapon?.gemPassive ?? 0} max={3} label={t("bench.refineLevel", { value: build.weapon?.gemPassive ?? 0, max: 3 })} />
          </li>
        </ul>
        <p className={b.note}>{t("solution.gemNote")}</p>
      </section>
      <div className={b.gear}>
        {entries.map((entry, position) => <GearSlot key={`${entry.gear.id}-${position}`} entry={entry} character={character} />)}
      </div>
    </div>

    {(setNames.length > 0 || unknownSets > 0) && <p className={b.sets}>
      <span>{t("solution.sets")}</span>
      {setNames.map((setName, position) => <span className={b.set} key={`${setName}-${position}`}>{setName}</span>)}
      {unknownSets > 0 && <span className={b.set}>{t("solution.unknownSets", { count: unknownSets })}</span>}
    </p>}

    <section className={b.panel} aria-labelledby="calc-bench-stats">
      <h4 id="calc-bench-stats" className={b.panelTitle}>{t("bench.statsTitle")}</h4>
      <StatBars evaluation={evaluation} breakdown={breakdown} required={required} />
      {breakdown.some((axis) => axis === null) && <p className={b.note}>{t("bench.breakdownUnavailable")}</p>}
    </section>
  </article>;
}
