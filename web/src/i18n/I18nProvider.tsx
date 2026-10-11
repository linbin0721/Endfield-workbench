import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { I18nextProvider } from "react-i18next";
import { useLocation, useNavigate, useNavigationType } from "react-router-dom";
import {
  applyDocumentLang,
  currentLocale,
  i18n,
  initializeI18n,
  loadNamespaces,
  namespacesForPath,
} from "./core";
import {
  localizePath,
  localeFromPathname,
  normalizeLocale,
  storeLocale,
  stripLocalePrefix,
  type Locale,
} from "./locale";

export type LocaleContextValue = {
  /** Locale currently rendered by the app, always one of SUPPORTED_LOCALES. */
  locale: Locale;
  /** True while the target language bundles of a switch are loading. */
  switching: boolean;
  /** Locale whose bundles failed to load; retry with `switchLocale(failedLocale)`. */
  failedLocale: Locale | null;
  /** Loads the language bundles, then changes language and localized URL. */
  switchLocale: (locale: Locale) => Promise<boolean>;
  /** Clears a previous switch failure message. */
  clearFailure: () => void;
};

const LocaleContext = createContext<LocaleContextValue | null>(null);

/**
 * Owns the active locale. The URL prefix is authoritative: a locale change in
 * the address bar (in-app navigation, back/forward, direct deep link) is synced
 * into i18next without remounting the route tree. Manual selections load the
 * target bundles first and keep the current page untouched on failure; a
 * generation counter discards the results of superseded rapid switches.
 */
export function I18nProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();
  const navigationType = useNavigationType();
  const [locale, setLocale] = useState<Locale>(() => normalizeLocale(i18n.language));
  const [switching, setSwitching] = useState(false);
  const [failedLocale, setFailedLocale] = useState<Locale | null>(null);
  const localeRef = useRef<Locale>(normalizeLocale(i18n.language));
  const generationRef = useRef(0);
  const locationRef = useRef(location);
  const ownNavigations = useRef(new Set<string>());

  useEffect(() => {
    locationRef.current = location;
  }, [location]);

  const syncFromI18n = useCallback(() => {
    const next = currentLocale();
    localeRef.current = next;
    applyDocumentLang(next);
    setLocale(next);
  }, []);

  useEffect(() => {
    const handleLanguageChanged = () => syncFromI18n();
    i18n.on("languageChanged", handleLanguageChanged);
    return () => {
      i18n.off("languageChanged", handleLanguageChanged);
    };
  }, [syncFromI18n]);

  useEffect(() => {
    let active = true;
    void initializeI18n().then(() => {
      if (active) syncFromI18n();
    });
    return () => {
      active = false;
    };
  }, [syncFromI18n]);

  const navigateToLocale = useCallback(
    (target: Locale) => {
      const current = locationRef.current;
      const pathname = localizePath(stripLocalePrefix(current.pathname), target);
      if (pathname === current.pathname) return;
      ownNavigations.current.add(pathname);
      navigate({ pathname, search: current.search, hash: current.hash });
    },
    [navigate],
  );

  const applyLocale = useCallback(
    async (target: Locale, options: { navigate: boolean; persist: boolean }): Promise<boolean> => {
      const generation = ++generationRef.current;
      if (target === localeRef.current) {
        setSwitching(false);
        setFailedLocale(null);
        if (options.persist) storeLocale(target);
        if (options.navigate) navigateToLocale(target);
        return true;
      }
      setSwitching(true);
      setFailedLocale(null);
      try {
        // The user may enter another tool while these resources are loading.
        let path: string;
        do {
          path = locationRef.current.pathname;
          await loadNamespaces(target, namespacesForPath(path));
          if (generation !== generationRef.current) return false;
        } while (path !== locationRef.current.pathname);
        if (generation !== generationRef.current) return false;
        await i18n.changeLanguage(target);
        if (generation !== generationRef.current) return false;
        localeRef.current = target;
        applyDocumentLang(target);
        setLocale(target);
        if (options.persist) storeLocale(target);
        if (options.navigate) navigateToLocale(target);
        return true;
      } catch (error) {
        if (generation !== generationRef.current) return false;
        console.warn(`i18n: failed to switch language to ${target}`, error);
        setFailedLocale(target);
        return false;
      } finally {
        if (generation === generationRef.current) setSwitching(false);
      }
    },
    [navigateToLocale],
  );

  const switchLocale = useCallback(
    (target: Locale) => applyLocale(target, { navigate: true, persist: true }),
    [applyLocale],
  );

  const clearFailure = useCallback(() => setFailedLocale(null), []);

  const urlLocale = localeFromPathname(location.pathname);
  useEffect(() => {
    if (!urlLocale) return;
    // An earlier switch's own push must not supersede a newer selection.
    // Back/forward navigation still takes precedence over pending selections.
    if (navigationType !== "POP" && ownNavigations.current.delete(location.pathname)) return;
    // Only an address bar locale that differs from the active language is a
    // real navigation (deep link, back/forward). An equal prefix is the result
    // of our own switch, so it must not cancel a newer pending switch.
    if (urlLocale === localeRef.current) return;
    void applyLocale(urlLocale, { navigate: false, persist: true });
  }, [urlLocale, location.pathname, navigationType, applyLocale]);

  // Preload the namespaces of the current tool for the active language. Tool
  // pages keep rendering while this happens, and already loaded bundles are
  // reused, so switching a running tool neither unmounts nor restarts it.
  useEffect(() => {
    void loadNamespaces(locale, namespacesForPath(location.pathname)).catch(() => undefined);
  }, [locale, location.pathname]);

  const value = useMemo<LocaleContextValue>(
    () => ({ locale, switching, failedLocale, switchLocale, clearFailure }),
    [clearFailure, failedLocale, locale, switchLocale, switching],
  );

  return (
    <LocaleContext.Provider value={value}>
      <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
    </LocaleContext.Provider>
  );
}

export function useLocale(): LocaleContextValue {
  const value = useContext(LocaleContext);
  if (!value) throw new Error("useLocale must be used inside <I18nProvider>");
  return value;
}
