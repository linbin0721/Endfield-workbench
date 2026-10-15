import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { localizePath, stripLocalePrefix, useAppTranslation } from "../i18n";
import { Drawer } from "../ui/Drawer/Drawer";
import { IconButton } from "../ui/IconButton/IconButton";
import { ChevronRightIcon, MenuIcon } from "../ui/icons";
import { LanguageSelect, LanguageStatus } from "./LanguageControls";
import { NAV_ITEMS } from "./navItems";
import styles from "./MobileMenu.module.css";

/** Menu button and drawer for narrow screens: navigation plus language. */
export function MobileMenu({ className }: { className?: string }) {
  const { t, locale } = useAppTranslation("common");
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const page = stripLocalePrefix(location.pathname);

  // Close after navigating to another page; a language switch keeps it open.
  useEffect(() => { setOpen(false); }, [page]);

  return <Drawer
    open={open}
    onOpenChange={setOpen}
    trigger={<IconButton className={className} label={t("nav.menu")} icon={<MenuIcon />} />}
    title={t("nav.menuTitle")}
    closeLabel={t("nav.close")}
  >
    <nav aria-label={t("nav.ariaLabel")}>
      <ul className={styles.list}>
        {NAV_ITEMS.map((item, index) => <li key={item.id}>
          <NavLink
            to={localizePath(item.path, locale)}
            end={item.end}
            className={styles.link}
            onClick={() => setOpen(false)}
          >
            <span className={styles.index} aria-hidden="true">{String(index).padStart(2, "0")}</span>
            <item.icon className={styles.icon} />
            <span className={styles.label}>{t(item.labelKey)}</span>
            <ChevronRightIcon className={styles.chevron} />
          </NavLink>
        </li>)}
      </ul>
    </nav>
    <section className={styles.language} aria-labelledby="menu-language-heading">
      <h2 id="menu-language-heading" className={styles.heading}>{t("language.label")}</h2>
      <LanguageSelect className={styles.select} />
      <LanguageStatus />
    </section>
  </Drawer>;
}
