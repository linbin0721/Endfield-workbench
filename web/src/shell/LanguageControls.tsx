import { LOCALE_LABELS, SUPPORTED_LOCALES, matchLocaleSegment, useAppTranslation, useLocale } from "../i18n";
import { Button } from "../ui/Button/Button";
import { GlobeIcon, RefreshIcon, WarningIcon } from "../ui/icons";
import { Select } from "../ui/Select/Select";
import styles from "./LanguageControls.module.css";

const OPTIONS = SUPPORTED_LOCALES.map((code) => ({
  value: code,
  // Each language is written in its own language and script.
  label: <span lang={code}>{LOCALE_LABELS[code]}</span>,
  textValue: LOCALE_LABELS[code],
}));

/** Interface language picker; the mounted page and its tasks stay as they are. */
export function LanguageSelect({ className }: { className?: string }) {
  const { t } = useAppTranslation("common");
  const { locale, switching, switchLocale } = useLocale();
  return <div className={[styles.select, className ?? ""].filter(Boolean).join(" ")} aria-busy={switching}>
    <Select
      value={locale}
      onValueChange={(value) => {
        const next = matchLocaleSegment(value);
        if (next && next !== locale) void switchLocale(next);
      }}
      options={OPTIONS}
      leading={<GlobeIcon />}
      aria-label={t("language.ariaLabel")}
    />
  </div>;
}

/**
 * Switching progress and the failure message with a retry, on a dark strip in
 * both themes. `floating` centres them under the top bar; otherwise they sit
 * in the flow (mobile menu).
 */
export function LanguageStatus({ floating = false }: { floating?: boolean }) {
  const { t } = useAppTranslation("common");
  const { switching, failedLocale, switchLocale } = useLocale();
  return <div className={floating ? styles.dock : styles.inline}>
    <div role="status" className={styles.slot}>
      {switching
        ? <p className={styles.strip} data-surface="dark"><span className={styles.progress} aria-hidden="true" />{t("language.switching")}</p>
        : null}
    </div>
    {failedLocale
      ? <div role="alert" className={[styles.strip, styles.error].join(" ")} data-surface="dark">
        <WarningIcon className={styles.icon} />
        <span className={styles.message}>{t("language.error")}</span>
        <Button variant="secondary" size="sm" icon={<RefreshIcon />} onClick={() => { void switchLocale(failedLocale); }}>
          {t("language.retry")}
        </Button>
      </div>
      : null}
  </div>;
}
