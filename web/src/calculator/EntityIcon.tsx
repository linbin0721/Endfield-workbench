import { useCallback, useEffect, useRef, useState } from "react";
import { useAppTranslation } from "../i18n";
import styles from "./EntityIcon.module.css";
import { getEntityMedia, type EntityKind } from "./media.ts";

type EntityIconProps = {
  kind: EntityKind;
  id: string;
  name: string;
  size?: 56 | 64 | 88;
  eager?: boolean;
  /** Weapon rarity (3–6): a coloured bar along the bottom edge. */
  rarity?: number;
};

function IconImage({ imageUrl, name, size, eager }: {
  imageUrl: string;
  name: string;
  size: 56 | 64 | 88;
  eager: boolean;
}) {
  const [ready, setReady] = useState(false);
  const imageRef = useRef<HTMLImageElement>(null);
  const activeRef = useRef(true);
  const attemptRef = useRef(0);
  const decodingRef = useRef(false);

  const revealImage = useCallback((image: HTMLImageElement) => {
    if (!activeRef.current || decodingRef.current || image.naturalWidth === 0) return;
    decodingRef.current = true;
    const attempt = ++attemptRef.current;
    const reveal = () => {
      if (activeRef.current && attempt === attemptRef.current && image === imageRef.current) setReady(true);
    };
    if (typeof image.decode !== "function") { reveal(); return; }
    try {
      // A rejected decode keeps the placeholder; no broken image is exposed.
      void image.decode().then(reveal, () => {});
    } catch {
      // Older or interrupted image decoders may throw synchronously.
    }
  }, []);

  useEffect(() => {
    activeRef.current = true;
    const image = imageRef.current;
    // A cached image can finish before the load handler is attached.
    if (image?.complete && image.naturalWidth > 0) revealImage(image);
    return () => {
      activeRef.current = false;
      attemptRef.current += 1;
      decodingRef.current = false;
    };
  }, [revealImage]);

  return <>
    <span className={styles.placeholder} hidden={ready} aria-hidden="true">
      {Array.from(name.trim())[0] ?? "?"}
    </span>
    <img ref={imageRef} src={imageUrl} alt="" width={size} height={size}
      className={ready ? `${styles.image} ${styles.ready}` : styles.image}
      loading={eager ? "eager" : "lazy"} fetchPriority={eager ? "high" : "auto"} decoding="async"
      onLoad={(event) => revealImage(event.currentTarget)} onError={() => {
        attemptRef.current += 1;
        if (activeRef.current) setReady(false);
      }} />
  </>;
}

/** Media is a presentation-only lookup; missing records never produce a guessed link. */
export default function EntityIcon({ kind, id, name, size = 64, eager = false, rarity }: EntityIconProps) {
  const { t } = useAppTranslation("calculator");
  if (!id) return null;
  const media = getEntityMedia(kind, id);
  const className = [styles.icon, size === 56 ? styles.small : size === 88 ? styles.large : "", rarity ? styles[`r${rarity}`] : ""].filter(Boolean).join(" ");
  if (!media) return <span className={className} role="img" aria-label={t("icon.missing", { name })}>
    <span className={styles.placeholder} aria-hidden="true">{Array.from(name.trim())[0] ?? "?"}</span>
  </span>;
  return <a className={className} href={media.detailUrl} target="_blank" rel="noopener noreferrer"
    aria-label={t("icon.open", { name })} title={t("icon.title", { name })}>
    <IconImage key={`${kind}:${id}:${media.imageUrl}`} imageUrl={media.imageUrl}
      name={name} size={size} eager={eager} />
  </a>;
}
