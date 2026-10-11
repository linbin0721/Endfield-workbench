import { currentLocale, i18n } from "./core";
import type { Locale } from "./locale";
import type { NameKind } from "./types";

/**
 * Looks up a game name from the `names` namespace by its original game ID.
 * Falls back to the caller-provided text when the namespace or the ID is
 * missing, so a partially loaded language never renders an empty label.
 */
export function localizedName(kind: NameKind, id: string, fallback: string): string {
  if (!id) return fallback;
  // The names namespace is grouped by kind, for example { "characters": { "<id>": "..." } }.
  const translated = i18n.t(`${kind}.${id}`, { ns: "names", defaultValue: fallback });
  return typeof translated === "string" && translated.length > 0 ? translated : fallback;
}

/** Locale-aware number formatting helper for pages that show raw numbers. */
export function formatNumber(
  value: number,
  options?: Intl.NumberFormatOptions,
  locale: Locale = currentLocale(),
): string {
  return new Intl.NumberFormat(locale, options).format(value);
}

/** Locale-aware date formatting helper for pages that show timestamps. */
export function formatDate(
  value: Date | number,
  options?: Intl.DateTimeFormatOptions,
  locale: Locale = currentLocale(),
): string {
  return new Intl.DateTimeFormat(locale, options).format(value);
}
