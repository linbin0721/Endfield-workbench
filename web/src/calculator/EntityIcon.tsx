import { useState } from "react";
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
  const [failed, setFailed] = useState(false);
  if (failed) return <span className="calc-icon-placeholder" aria-hidden="true">
    {Array.from(name.trim())[0] ?? "?"}
  </span>;
  return <img src={imageUrl} alt="" width={size} height={size}
    loading={eager ? "eager" : "lazy"} decoding="async" onError={() => setFailed(true)} />;
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
