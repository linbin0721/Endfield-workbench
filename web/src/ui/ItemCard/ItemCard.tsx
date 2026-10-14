import type { ReactNode } from "react";
import styles from "./ItemCard.module.css";

export type Rarity = 3 | 4 | 5 | 6;

type ItemCardProps = {
  name: string;
  rarity: Rarity;
  level?: number;
  /** Image element (icon); the card supplies the frame and rarity bar. */
  image?: ReactNode;
  /** Small marker in the top-right corner, e.g. the wearer's avatar. */
  badge?: ReactNode;
  selected?: boolean;
  /** Makes the card a toggle button. */
  onSelect?: () => void;
  showName?: boolean;
};

/** Square item tile with a rarity bar along the bottom and "LV.xx" in the corner. */
export function ItemCard({ name, rarity, level, image, badge, selected = false, onSelect, showName = true }: ItemCardProps) {
  const tile = <>
    <span className={styles.art}>{image}</span>
    {level !== undefined ? <span className={styles.level}><small>LV.</small>{level}</span> : null}
    {badge ? <span className={styles.badge}>{badge}</span> : null}
    <span className={styles.bar} aria-hidden="true" />
  </>;
  const classes = [styles.tile, styles[`r${rarity}`], selected ? styles.selected : ""].filter(Boolean).join(" ");
  return <figure className={styles.card}>
    {onSelect
      ? <button type="button" className={classes} aria-pressed={selected} aria-label={name} onClick={onSelect}>{tile}</button>
      : <span className={classes} role="img" aria-label={name}>{tile}</span>}
    {showName ? <figcaption className={styles.name}>{name}</figcaption> : null}
  </figure>;
}
