import { useCallback, useEffect, useRef, useState } from "react";
import { getEntityMedia, type EntityKind } from "./media.ts";

type EntityIconProps = {
  kind: EntityKind;
  id: string;
  name: string;
  size?: 56 | 64;
  eager?: boolean;
};

function IconImage({ imageUrl, name, size, eager }: {
  imageUrl: string;
  name: string;
  size: 56 | 64;
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
    <span className="calc-icon-placeholder" hidden={ready} aria-hidden="true">
      {Array.from(name.trim())[0] ?? "?"}
    </span>
    <img ref={imageRef} src={imageUrl} alt="" width={size} height={size}
      className={ready ? "calc-icon-image-ready" : undefined}
      loading={eager ? "eager" : "lazy"} fetchPriority={eager ? "high" : "auto"} decoding="async"
      onLoad={(event) => revealImage(event.currentTarget)} onError={() => {
        attemptRef.current += 1;
        if (activeRef.current) setReady(false);
      }} />
  </>;
}

/** Media is a presentation-only lookup; missing records never produce a guessed link. */
export default function EntityIcon({ kind, id, name, size = 64, eager = false }: EntityIconProps) {
  if (!id) return null;
  const media = getEntityMedia(kind, id);
  const className = `calc-entity-icon${size === 56 ? " calc-entity-icon-small" : ""}`;
  if (!media) return <span className={className} role="img" aria-label={`${name}：暂无图标`}>
    <span className="calc-icon-placeholder" aria-hidden="true">{Array.from(name.trim())[0] ?? "?"}</span>
  </span>;
  return <a className={className} href={media.detailUrl} target="_blank" rel="noopener noreferrer"
    aria-label={`${name}：查看资料（在新标签页打开）`} title={`${name} · 查看资料`}>
    <IconImage key={`${kind}:${id}:${media.imageUrl}`} imageUrl={media.imageUrl}
      name={name} size={size} eager={eager} />
  </a>;
}
