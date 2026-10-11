import type { ChangeEvent } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import {
  LOCALE_LABELS,
  SUPPORTED_LOCALES,
  localizePath,
  matchLocaleSegment,
  useAppTranslation,
  useLocale,
} from "./i18n";

const navClassName = ({ isActive }: { isActive: boolean }) => isActive ? "active" : undefined;

export default function SiteLayout() {
  const { t } = useAppTranslation("common");
  const { locale, switching, failedLocale, switchLocale } = useLocale();
  const localized = (path: string) => localizePath(path, locale);

  const handleLanguageChange = (event: ChangeEvent<HTMLSelectElement>) => {
    const next = matchLocaleSegment(event.target.value);
    if (next && next !== locale) void switchLocale(next);
  };

  return <div className="page">
    <header className="site-header">
      <Link className="brand" to={localized("/")}>{t("brand")}</Link>
      <nav className="site-nav" aria-label={t("nav.ariaLabel")}>
        <NavLink to={localized("/")} end className={navClassName}>{t("nav.home")}</NavLink>
        <NavLink to={localized("/balloon")} className={navClassName}>{t("nav.balloon")}</NavLink>
        <NavLink to={localized("/circuit")} className={navClassName}>{t("nav.circuit")}</NavLink>
        <NavLink to={localized("/325")} className={navClassName}>{t("nav.calculator")}</NavLink>
      </nav>
      <div className="site-language">
        <label className="visually-hidden" htmlFor="site-language-select">{t("language.label")}</label>
        <select
          id="site-language-select"
          className="language-select"
          aria-label={t("language.ariaLabel")}
          aria-busy={switching}
          value={locale}
          onChange={handleLanguageChange}
        >
          {SUPPORTED_LOCALES.map((code) =>
            <option key={code} value={code} lang={code}>{LOCALE_LABELS[code]}</option>)}
        </select>
        {switching
          ? <span className="language-status" role="status">{t("language.switching")}</span>
          : null}
        {failedLocale
          ? <span className="language-status language-error" role="alert">
            {t("language.error")}{" "}
            <button
              type="button"
              className="text-button"
              onClick={() => { void switchLocale(failedLocale); }}
            >{t("language.retry")}</button>
          </span>
          : null}
      </div>
    </header>
    <main><Outlet /></main>
    <footer>{t("footer")}</footer>
  </div>;
}
