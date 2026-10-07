/** Presentation only. Never import this registry into calculation or Worker modules. */
import registry from "./media/registry.json";

export type EntityKind = "characters" | "weapons" | "equipment";
export interface EntityMedia {
  imageUrl: string;
  detailUrl: string;
}

const images = import.meta.glob<string>("./media/icons/**/*.webp", {
  eager: true,
  // Emit even small icons as hashed files; URLs do not download images until displayed.
  query: "?url&no-inline",
  import: "default",
});
const entries: Record<EntityKind, Record<string, { file: string; detailUrl: string }>> = registry;

export function getEntityMedia(kind: EntityKind, id: string): EntityMedia | undefined {
  const entry = entries[kind][id];
  if (!entry) return undefined;
  const imageUrl = images[`./media/${entry.file}`];
  return imageUrl ? { imageUrl, detailUrl: entry.detailUrl } : undefined;
}
