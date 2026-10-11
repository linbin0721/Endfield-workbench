/**
 * Public i18n surface of the workbench.
 *
 * Framework:   i18n, initializeI18n, loadNamespaces, namespacesForPath, applyDocumentLang
 * Routing:     Locale, SUPPORTED_LOCALES, DEFAULT_LOCALE, LOCALE_LABELS,
 *              normalizeLocale, matchLocaleSegment, localeFromPathname,
 *              stripLocalePrefix, localizePath, detectPreferredLocale
 * React:       I18nProvider, useLocale, useAppTranslation
 * Messages:    useMessages, msg, isLocalizedText, LocalizedText, MessageText
 * Formatting:  localizedName, formatNumber, formatDate
 */
export {
  DEFAULT_LOCALE,
  LOCALE_LABELS,
  LOCALE_STORAGE_KEY,
  SUPPORTED_LOCALES,
  detectPreferredLocale,
  localizePath,
  localeFromPathname,
  matchLocaleSegment,
  normalizeLocale,
  readStoredLocale,
  storeLocale,
  stripLocalePrefix,
  type Locale,
} from "./locale";
export {
  applyDocumentLang,
  currentLocale,
  i18n,
  initializeI18n,
  loadNamespaces,
  namespacesForPath,
} from "./core";
export { formatDate, formatNumber, localizedName } from "./helpers";
export { I18nProvider, useLocale, type LocaleContextValue } from "./I18nProvider";
export { useAppTranslation } from "./useAppTranslation";
export {
  isLocalizedText,
  msg,
  useMessages,
  type LocalizedText,
  type MessageKind,
  type MessageRenderer,
  type MessageText,
} from "./messages";
export {
  buildTemplateIndex,
  matchTemplate,
  templateParams,
  type MessageTemplate,
  type MessageTemplateIndex,
  type TemplateMatch,
} from "./messageTemplates";
export { NAMESPACES, type NameBundle, type NameKind, type Namespace } from "./types";
