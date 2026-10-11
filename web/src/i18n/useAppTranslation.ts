import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { normalizeLocale, type Locale } from "./locale";
import type { Namespace } from "./types";

/**
 * Subscribes a component to the active language and returns i18next's normal
 * translation function plus the canonical locale. Language changes re-render
 * the caller without unmounting it, so tool state, requests and workers survive.
 */
export function useAppTranslation(namespace: Namespace): { t: TFunction; locale: Locale } {
  const { t, i18n } = useTranslation(namespace);
  const locale = normalizeLocale(i18n.resolvedLanguage ?? i18n.language);
  return { t, locale };
}
