import { useAppTranslation } from "../i18n";
import { Button } from "../ui/Button/Button";
import { RefreshIcon } from "../ui/icons";
import { Notice } from "../ui/Notice/Notice";
import styles from "./LoadingState.module.css";

type LoadingStateProps = {
  /** Shows the error with a retry instead of the progress bar. */
  failed?: boolean;
  /** Error text; defaults to the language loading error. */
  message?: string;
  onRetry?: () => void;
};

/** Placeholder while a page's language resources or code load. */
export function LoadingState({ failed = false, message, onRetry }: LoadingStateProps) {
  const { t } = useAppTranslation("common");
  if (failed) {
    return <div className={styles.box}>
      <Notice
        tone="danger"
        role="alert"
        title={message ?? t("language.error")}
        action={onRetry
          ? <Button variant="secondary" size="sm" icon={<RefreshIcon />} onClick={onRetry}>{t("language.retry")}</Button>
          : null}
      />
    </div>;
  }
  return <div className={styles.box} role="status">
    <p className={styles.label}><span className={styles.slashes} aria-hidden="true">//</span>{t("loading")}</p>
    <span className={styles.track} aria-hidden="true"><span className={styles.bar} /></span>
  </div>;
}
