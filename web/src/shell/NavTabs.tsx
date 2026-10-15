import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { localizePath, useAppTranslation } from "../i18n";
import { NAV_ITEMS } from "./navItems";
import styles from "./NavTabs.module.css";

type Indicator = { left: number; width: number; visible: boolean };

/**
 * Desktop tab strip. The yellow block is one element that slides to the
 * active tab; it is re-measured when the route, the language (label widths)
 * or the strip size changes, and stays hidden on pages without a tab (404).
 */
export function NavTabs() {
  const { t, locale } = useAppTranslation("common");
  const location = useLocation();
  const listRef = useRef<HTMLUListElement>(null);
  const [indicator, setIndicator] = useState<Indicator>({ left: 0, width: 0, visible: false });
  const [animated, setAnimated] = useState(false);

  useLayoutEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const measure = () => {
      const active = list.querySelector<HTMLElement>('a[aria-current="page"]');
      setIndicator((previous) => active && active.offsetWidth
        ? { left: active.offsetLeft, width: active.offsetWidth, visible: true }
        : { ...previous, visible: false });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(list);
    list.querySelectorAll("a").forEach((link) => observer.observe(link));
    return () => observer.disconnect();
  }, [location.pathname, locale]);

  // The first placement is instant; only later moves slide.
  useEffect(() => {
    if (animated || !indicator.visible) return;
    const frame = requestAnimationFrame(() => setAnimated(true));
    return () => cancelAnimationFrame(frame);
  }, [animated, indicator.visible]);

  return <nav className={styles.nav} aria-label={t("nav.ariaLabel")}>
    <ul ref={listRef} className={styles.list}>
      <li
        className={[styles.indicator, animated ? styles.animated : ""].filter(Boolean).join(" ")}
        style={{ transform: `translateX(${indicator.left}px)`, width: indicator.width, opacity: indicator.visible ? 1 : 0 }}
        aria-hidden="true"
      />
      {NAV_ITEMS.map((item) => <li key={item.id}>
        <NavLink to={localizePath(item.path, locale)} end={item.end} className={styles.tab}>
          <item.icon className={styles.icon} />
          <span>{t(item.labelKey)}</span>
        </NavLink>
      </li>)}
    </ul>
  </nav>;
}
