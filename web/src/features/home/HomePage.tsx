import { useEffect, type CSSProperties } from "react";
import { Link } from "react-router-dom";
import { localizePath, useAppTranslation } from "../../i18n";
import { TOOLS } from "../../tools/registry";
import { ArrowRightIcon } from "../../ui/icons";
import { Contours } from "./Contours";
import styles from "./HomePage.module.css";

const pad = (value: number) => String(value).padStart(2, "0");

export default function HomePage() {
  const { t, locale } = useAppTranslation("common");
  useEffect(() => { document.title = t("home.title"); }, [t, locale]);
  return <div className={styles.home}>
    <section className={styles.hero} aria-labelledby="home-heading">
      <div className={styles.backdrop} aria-hidden="true">
        <Contours className={styles.contours} lineClassName={styles.contourLine} pulseClassName={styles.contourPulse} />
        <span className={styles.scan} />
        <span className={styles.watermark}>{t("home.watermark")}</span>
      </div>
      <div className={styles.heroContent}>
        <p className={styles.eyebrow}><span className={styles.code} aria-hidden="true" />{t("home.eyebrow")}</p>
        <h1 id="home-heading" className={styles.title}>
          <span className={styles.slashes} aria-hidden="true">//</span>
          <span className={styles.titleText}>{t("home.heading")}</span>
        </h1>
        <p className={styles.intro}>{t("home.intro")}</p>
      </div>
      <p className={styles.readout} aria-hidden="true">
        <span className={styles.readoutDot} />{t("home.readout", { total: pad(TOOLS.length) })}
      </p>
      <span className={styles.ruler} aria-hidden="true" />
    </section>
    <ul className={styles.cards}>
      {TOOLS.map((tool, index) => <li key={tool.id} className={styles.cardItem} style={{ "--i": index } as CSSProperties}>
        <Link className={styles.card} to={localizePath(`/${tool.segment}`, locale)}>
          <span className={styles.cardTop}>
            <span className={styles.index} aria-hidden="true">{pad(index + 1)}</span>
            <span className={styles.tag}>{t(tool.tagKey)}</span>
            <span className={styles.status}><i className={styles.statusDot} aria-hidden="true" />{t("home.statusAvailable")}</span>
          </span>
          <span className={styles.iconBox} aria-hidden="true"><tool.icon /></span>
          <h2 className={styles.cardTitle}>{t(tool.nameKey)}</h2>
          <p className={styles.cardText}>{t(tool.descriptionKey)}</p>
          <span className={styles.action}>{t("home.openTool")}<ArrowRightIcon className={styles.arrow} /></span>
          <span className={styles.sweep} aria-hidden="true" />
        </Link>
      </li>)}
    </ul>
  </div>;
}
