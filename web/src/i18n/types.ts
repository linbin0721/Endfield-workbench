/**
 * Namespaces shipped with the workbench. Every locale folder mirrors this list,
 * and all six resources are required. Missing resources fail before the tool
 * mounts or before the active language changes.
 */
export const NAMESPACES = ["common", "messages", "balloon", "circuit", "calculator", "names"] as const;

export type Namespace = (typeof NAMESPACES)[number];

/**
 * Game entity groups of the `names` namespace. Keys are the original game IDs,
 * values the localized display names.
 */
export type NameKind = "characters" | "weapons" | "equipment" | "sets";

export type NameBundle = Partial<Record<NameKind, Record<string, string>>>;
