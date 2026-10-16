import { useMemo, useState } from "react";
import EntityIcon from "../../calculator/EntityIcon.tsx";
import { getEntityMedia } from "../../calculator/media.ts";
import type { Character } from "../../calculator/types.ts";
import { useAppTranslation } from "../../i18n";
import { Button } from "../../ui/Button/Button";
import { Dialog } from "../../ui/Dialog/Dialog";
import { SearchIcon } from "../../ui/icons";
import { characterDisplayName } from "./model";
import s from "./calculator.module.css";

function Avatar({ id, name }: { id: string; name: string }) {
  const url = getEntityMedia("characters", id)?.imageUrl;
  return <span className={s.avatar} aria-hidden="true">
    {url ? <img src={url} alt="" width={56} height={56} loading="lazy" decoding="async" /> : Array.from(name.trim())[0] ?? "?"}
  </span>;
}

/**
 * Current operator with a "change" button that opens an avatar grid with a
 * name search. Picking an operator calls `onSelect` (which resets the search
 * exactly like the old select) and closes the dialog.
 */
export function CharacterPicker({ id, labelId, character, characters, onSelect }: {
  id: string;
  labelId: string;
  character: Character;
  characters: readonly Character[];
  onSelect: (characterId: string) => void;
}) {
  const { t } = useAppTranslation("calculator");
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const name = characterDisplayName(character);
  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return characters.filter((item) => !needle ||
      characterDisplayName(item).toLowerCase().includes(needle) || item.name.toLowerCase().includes(needle));
  }, [characters, query]);
  return <div className={s.operator} role="group" aria-labelledby={labelId}>
    <EntityIcon kind="characters" id={character.id} name={name} eager />
    <p className={s.operatorName}>{name}</p>
    <Dialog
      open={open}
      onOpenChange={(next) => { setOpen(next); if (!next) setQuery(""); }}
      trigger={<Button id={id} variant="secondary" size="sm" icon={<SearchIcon />}>{t("picker.change")}</Button>}
      title={t("picker.title")}
      closeLabel={t("picker.close")}
    >
      <input className={`${s.input} ${s.search}`} type="search" value={query} autoComplete="off"
        placeholder={t("picker.search")} aria-label={t("picker.search")} onChange={(event) => setQuery(event.target.value)} />
      {matches.length
        ? <div className={s.grid}>
          {matches.map((item) => {
            const itemName = characterDisplayName(item);
            return <button key={item.id} type="button" className={s.pick} aria-pressed={item.id === character.id}
              onClick={() => { onSelect(item.id); setOpen(false); setQuery(""); }}>
              <Avatar id={item.id} name={itemName} />
              <span>{itemName}</span>
            </button>;
          })}
        </div>
        : <p className={s.empty} role="status">{t("picker.empty")}</p>}
    </Dialog>
  </div>;
}
