import type { MouseEvent } from "react";
import { Link, Outlet } from "react-router-dom";
import { localizePath, useAppTranslation } from "../i18n";
import { ThemeToggle } from "../ui/ThemeToggle/ThemeToggle";
import { BrandMark } from "./BrandMark";
import { LanguageSelect, LanguageStatus } from "./LanguageControls";
import { MobileMenu } from "./MobileMenu";
import { NavTabs } from "./NavTabs";
import styles from "./SiteLayout.module.css";

/** Moves focus to the page content without adding a hash to the URL. */
function skipToContent(event: MouseEvent<HTMLAnchorElement>) {
  event.preventDefault();
  document.getElementById("main")?.focus();
}

export default function SiteLayout() {
  const { t, locale } = useAppTranslation("common");
  return <div className={styles.shell}>
    <a className={styles.skip} href="#main" onClick={skipToContent}>{t("nav.skip")}</a>
    <header className={styles.bar}>
      <div className={styles.barInner}>
        <MobileMenu className={styles.mobileOnly} />
        <Link className={styles.brand} to={localizePath("/", locale)}>
          <BrandMark />
          <span className={styles.brandName}>{t("brand")}</span>
        </Link>
        <div className={styles.desktopOnly}><NavTabs /></div>
        <div className={styles.actions}>
          <LanguageSelect className={styles.desktopOnly} />
          <ThemeToggle toDarkLabel={t("theme.toDark")} toLightLabel={t("theme.toLight")} />
        </div>
      </div>
      <LanguageStatus floating />
    </header>
    <main id="main" tabIndex={-1} className={styles.main}><Outlet /></main>
    <footer className={styles.footer}>
      <div className={styles.footerInner}>
        <span className={styles.footerBrand}><BrandMark className={styles.footerMark} />{t("brand")}</span>
        <span className={styles.footerNote}>{t("footer")}</span>
      </div>
    </footer>
  </div>;
}
