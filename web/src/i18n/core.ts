import { createInstance } from "i18next";
import { initReactI18next } from "react-i18next";
import {
  DEFAULT_LOCALE,
  SUPPORTED_LOCALES,
  detectPreferredLocale,
  normalizeLocale,
  stripLocalePrefix,
  type Locale,
} from "./locale";
import { NAMESPACES, type Namespace } from "./types";

type LocaleResource = Record<string, unknown>;

/**
 * Translation JSON lives next to the code and is bundled by Vite as hashed
 * assets, one JSON per locale/namespace. Only their hashed URLs enter the main
 * bundle. Fetch failures are retryable without reloading a mounted tool.
 */
const localeUrls = import.meta.glob<string>("./locales/*/*.json", {
  eager: true,
  query: "?url&no-inline",
  import: "default",
});

/** Single i18next instance shared by the app and by consumers of this module. */
export const i18n = createInstance();

const pendingLoads = new Map<string, Promise<void>>();
let bootstrapPromise: Promise<Locale> | null = null;

function currentPathname(): string {
  return typeof window === "undefined" ? "/" : window.location.pathname;
}

/** Keeps <html lang> in sync; called during bootstrap and on every language change. */
export function applyDocumentLang(locale: Locale): void {
  if (typeof document !== "undefined") document.documentElement.lang = locale;
}

/** Current canonical locale of the i18next instance. */
export function currentLocale(): Locale {
  return normalizeLocale(i18n.resolvedLanguage ?? i18n.language);
}

/**
 * Namespaces needed by a route. Tool pages preload only their own module, the
 * calculator additionally needs the game name tables.
 */
export function namespacesForPath(pathname: string): Namespace[] {
  const path = stripLocalePrefix(pathname || "/");
  if (path === "/325" || path.startsWith("/325/")) return ["common", "messages", "calculator", "names"];
  if (path === "/balloon" || path.startsWith("/balloon/")) return ["common", "messages", "balloon"];
  if (path === "/circuit" || path.startsWith("/circuit/")) return ["common", "messages", "circuit"];
  return ["common", "messages"];
}

function loadNamespace(locale: Locale, namespace: Namespace): Promise<void> {
  if (i18n.hasResourceBundle(locale, namespace)) return Promise.resolve();
  const key = `${locale}/${namespace}`;
  const running = pendingLoads.get(key);
  if (running) return running;
  const url = localeUrls[`./locales/${locale}/${namespace}.json`];
  if (!url) return Promise.reject(new Error(`Missing language resource: ${key}`));
  const task = fetchResource(url)
    .then((resource) => {
      i18n.addResourceBundle(locale, namespace, resource, true, true);
    })
    .catch((error: unknown) => {
      // Allow a later retry (for example the language selector retry button).
      pendingLoads.delete(key);
      throw error;
    });
  pendingLoads.set(key, task);
  return task;
}

async function fetchResource(url: string): Promise<LocaleResource> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10_000);
  try {
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) throw new Error(`Language resource HTTP ${response.status}`);
    const resource: unknown = await response.json();
    if (!resource || typeof resource !== "object" || Array.isArray(resource)) {
      throw new Error("Invalid language resource");
    }
    return resource as LocaleResource;
  } finally { clearTimeout(timer); }
}

async function loadNamespacesNow(locale: Locale, namespaces: readonly Namespace[]): Promise<void> {
  const targets = [...new Set(namespaces)];
  const locales = locale === DEFAULT_LOCALE ? [locale] : [locale, DEFAULT_LOCALE];
  await Promise.all(locales.flatMap((target) => targets.map((namespace) => loadNamespace(target, namespace))));
}

/**
 * Loads the requested namespaces for a locale. Simplified Chinese is loaded as
 * the fallback bundle of the same namespace, so partially translated locales
 * never show raw keys. Missing or failed resources use the localized recovery
 * UI; a partial target language is never applied.
 */
export async function loadNamespaces(locale: Locale, namespaces: readonly Namespace[]): Promise<void> {
  await initializeI18n();
  await loadNamespacesNow(locale, namespaces);
}

async function bootstrap(): Promise<Locale> {
  const locale = detectPreferredLocale(currentPathname());
  if (!i18n.isInitialized) {
    await i18n.use(initReactI18next).init({
      lng: locale,
      fallbackLng: DEFAULT_LOCALE,
      supportedLngs: [...SUPPORTED_LOCALES],
      ns: [...NAMESPACES],
      defaultNS: "common",
      resources: {},
      returnNull: false,
      interpolation: { escapeValue: false },
      react: {
        useSuspense: false,
        bindI18n: "languageChanged loaded",
        bindI18nStore: "added removed",
      },
    });
  }
  await loadNamespacesNow(locale, namespacesForPath(currentPathname()));
  applyDocumentLang(locale);
  return locale;
}

/**
 * Initializes i18next and preloads the namespaces of the first route. Must be
 * awaited before React mounts. Startup failures use the small recovery screen.
 */
export function initializeI18n(): Promise<Locale> {
  bootstrapPromise ??= bootstrap().catch((error: unknown) => {
    bootstrapPromise = null;
    throw error;
  });
  return bootstrapPromise;
}
