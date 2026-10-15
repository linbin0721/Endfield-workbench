import { useEffect } from "react";
import { Link } from "react-router-dom";
import { localizePath, useAppTranslation } from "../i18n";
import { TOOLS } from "../tools/registry";
import { ButtonContent, buttonClassName } from "../ui/Button/Button";
import { ArrowRightIcon } from "../ui/icons";
import styles from "./NotFoundPage.module.css";

/** "Signal lost" screen for unknown addresses, with a way back to every tool. */
export default function NotFoundPage() {
  const { t, locale } = useAppTranslation("common");
  useEffect(() => { document.title = t("notFound.title"); }, [t, locale]);
  return <section className={styles.page} aria-labelledby="not-found-heading">
    <div className={styles.signal} aria-hidden="true">
      <span className={styles.digits} data-text="404">404</span>
      <span className={styles.cursor} />
      <span className={styles.noise} />
    </div>
    <div className={styles.copy}>
      <p className={styles.eyebrow}><span className={styles.dot} />{t("notFound.eyebrow")}</p>
      <h1 id="not-found-heading" className={styles.title}>
        <span className={styles.slashes} aria-hidden="true">//</span>{t("notFound.heading")}
      </h1>
      <p className={styles.message}>{t("notFound.message")}</p>
      <Link className={buttonClassName({ variant: "accent" })} to={localizePath("/", locale)}>
        <ButtonContent icon={<ArrowRightIcon />}>{t("notFound.back")}</ButtonContent>
      </Link>
      <nav className={styles.tools} aria-labelledby="not-found-tools">
        <h2 id="not-found-tools" className={styles.toolsLabel}>{t("notFound.tools")}</h2>
        <ul className={styles.toolList}>
          {TOOLS.map((tool) => <li key={tool.id}>
            <Link className={styles.toolLink} to={localizePath(`/${tool.segment}`, locale)}>
              <tool.icon className={styles.toolIcon} />{t(tool.navKey)}
            </Link>
          </li>)}
        </ul>
      </nav>
    </div>
  </section>;
}
