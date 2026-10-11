/** Interface languages supported by the workbench, in selector order. */
export type Locale = "zh-CN" | "en" | "ja" | "ko";

export const DEFAULT_LOCALE: Locale = "zh-CN";

export const SUPPORTED_LOCALES = ["zh-CN", "en", "ja", "ko"] as const satisfies readonly Locale[];

/** Each language is always written in its own language, so it is not translated. */
export const LOCALE_LABELS: Record<Locale, string> = {
  "zh-CN": "简体中文",
  en: "English",
  ja: "日本語",
  ko: "한국어",
};

export const LOCALE_STORAGE_KEY = "endfield-workbench.locale";

/**
 * Maps a BCP-47 language tag to a supported locale. Chinese regions and scripts
 * all map to zh-CN; en/ja/ko match on their base language; everything else is
 * unknown and therefore reported as `null` by the internal matcher.
 */
function matchLanguageTag(tag: string | null | undefined): Locale | null {
  const normalized = String(tag ?? "").trim().toLowerCase();
  if (!normalized) return null;
  const base = normalized.split(/[-_]/)[0];
  if (base === "zh") return "zh-CN";
  if (base === "en") return "en";
  if (base === "ja") return "ja";
  if (base === "ko") return "ko";
  return null;
}

/** Normalizes any language tag; unknown languages fall back to Simplified Chinese. */
export function normalizeLocale(tag: string | null | undefined): Locale {
  return matchLanguageTag(tag) ?? DEFAULT_LOCALE;
}

/**
 * Strict match for a URL path segment: only the exact supported prefixes
 * (case-insensitive) are accepted, so unknown routes keep returning 404.
 */
export function matchLocaleSegment(segment: string | null | undefined): Locale | null {
  const normalized = String(segment ?? "").trim().toLowerCase();
  if (!normalized) return null;
  return SUPPORTED_LOCALES.find((locale) => locale.toLowerCase() === normalized) ?? null;
}

/** Returns the locale encoded in the first path segment, or null when absent. */
export function localeFromPathname(pathname: string): Locale | null {
  const segment = String(pathname ?? "").split("/")[1] ?? "";
  return matchLocaleSegment(segment);
}

/** Removes a leading locale prefix; unknown prefixes are left untouched. */
export function stripLocalePrefix(pathname: string): string {
  const path = String(pathname ?? "");
  const locale = localeFromPathname(path);
  if (!locale) return path.startsWith("/") ? path : `/${path}`;
  const rest = path.slice(1 + locale.length);
  if (!rest) return "/";
  return rest.startsWith("/") ? rest : `/${rest}`;
}

/**
 * Builds the localized form of an absolute app path. Query string and hash are
 * preserved, so language switches keep deep-link state.
 */
export function localizePath(path: string, locale: Locale): string {
  const raw = String(path ?? "");
  const hashIndex = raw.indexOf("#");
  const hash = hashIndex >= 0 ? raw.slice(hashIndex) : "";
  const withoutHash = hashIndex >= 0 ? raw.slice(0, hashIndex) : raw;
  const queryIndex = withoutHash.indexOf("?");
  const query = queryIndex >= 0 ? withoutHash.slice(queryIndex) : "";
  const pathname = queryIndex >= 0 ? withoutHash.slice(0, queryIndex) : withoutHash;
  const rest = stripLocalePrefix(pathname.startsWith("/") ? pathname : `/${pathname}`);
  const localized = rest === "/" ? `/${locale}` : `/${locale}${rest}`;
  return `${localized}${query}${hash}`;
}

function safeStorage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    // Blocked storage (private mode, disabled cookies) must never break startup.
    return null;
  }
}

/** Reads the saved preference; corrupted or blocked storage returns null. */
export function readStoredLocale(): Locale | null {
  try {
    const stored = safeStorage()?.getItem(LOCALE_STORAGE_KEY);
    return stored ? matchLanguageTag(stored) : null;
  } catch {
    return null;
  }
}

/** Persists the preference; storage errors are ignored on purpose. */
export function storeLocale(locale: Locale): void {
  try {
    safeStorage()?.setItem(LOCALE_STORAGE_KEY, locale);
  } catch {
    // Ignore: the URL and browser languages still keep the page usable.
  }
}

/**
 * Preference order: URL prefix, saved preference, navigator.languages, zh-CN.
 * A browser language list without en/ja/ko/zh entries also falls back to zh-CN.
 */
export function detectPreferredLocale(pathname?: string): Locale {
  const path = pathname ?? (typeof window === "undefined" ? "/" : window.location.pathname);
  const fromPath = localeFromPathname(path);
  if (fromPath) return fromPath;
  const stored = readStoredLocale();
  if (stored) return stored;
  const candidates =
    typeof navigator === "undefined"
      ? []
      : navigator.languages?.length
        ? navigator.languages
        : [navigator.language];
  for (const candidate of candidates) {
    const matched = matchLanguageTag(candidate);
    if (matched) return matched;
  }
  return DEFAULT_LOCALE;
}
