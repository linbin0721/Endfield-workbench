import { useEffect } from "react";
import { Link } from "react-router-dom";
import { localizePath, useAppTranslation } from "./i18n";

export default function HomePage() {
  const { t, locale } = useAppTranslation("common");
  useEffect(() => { document.title = t("home.title"); }, [t, locale]);
  return <div className="landing-page">
    <div className="intro home-intro">
      <span className="eyebrow">{t("home.eyebrow")}</span>
      <h1>{t("home.heading")}</h1>
      <p>{t("home.intro")}</p>
    </div>
    <div className="puzzle-cards">
      <Link className="puzzle-card available" to={localizePath("/balloon", locale)}>
        <span className="puzzle-card-status">{t("home.statusAvailable")}</span>
        <h2>{t("home.balloon.name")}</h2>
        <p>{t("home.balloon.description")}</p>
        <span className="puzzle-card-action">{t("home.openTool")}</span>
      </Link>
      <Link className="puzzle-card available" to={localizePath("/circuit", locale)}>
        <span className="puzzle-card-status">{t("home.statusAvailable")}</span>
        <h2>{t("home.circuit.name")}</h2>
        <p>{t("home.circuit.description")}</p>
        <span className="puzzle-card-action">{t("home.openTool")}</span>
      </Link>
      <Link className="puzzle-card available" to={localizePath("/325", locale)}>
        <span className="puzzle-card-status">{t("home.statusAvailable")}</span>
        <h2>{t("home.calculator.name")}</h2>
        <p>{t("home.calculator.description")}</p>
        <span className="puzzle-card-action">{t("home.openTool")}</span>
      </Link>
    </div>
  </div>;
}
