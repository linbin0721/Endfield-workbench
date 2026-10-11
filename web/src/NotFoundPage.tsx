import { useEffect } from "react";
import { Link } from "react-router-dom";
import { localizePath, useAppTranslation } from "./i18n";

export default function NotFoundPage() {
  const { t, locale } = useAppTranslation("common");
  useEffect(() => { document.title = t("notFound.title"); }, [t, locale]);
  return <div className="not-found-page">
    <span className="eyebrow">{t("notFound.eyebrow")}</span>
    <h1>{t("notFound.heading")}</h1>
    <p className="muted">{t("notFound.message")}</p>
    <Link className="button primary" to={localizePath("/", locale)}>{t("notFound.back")}</Link>
  </div>;
}
