import type { ReactNode } from "react";
import { CheckIcon, InfoIcon, WarningIcon } from "../icons";
import styles from "./Notice.module.css";

export type NoticeTone = "info" | "success" | "warning" | "danger";

type NoticeProps = {
  tone?: NoticeTone;
  title?: ReactNode;
  children?: ReactNode;
  /** Pass "status" or "alert" when the notice appears in response to an action. */
  role?: "status" | "alert";
  action?: ReactNode;
};

const ICONS: Record<NoticeTone, ReactNode> = {
  info: <InfoIcon />,
  success: <CheckIcon />,
  warning: <WarningIcon />,
  danger: <WarningIcon />,
};

export function Notice({ tone = "info", title, children, role, action }: NoticeProps) {
  return <div className={[styles.notice, styles[tone]].join(" ")} role={role}>
    <span className={styles.icon} aria-hidden="true">{ICONS[tone]}</span>
    <div className={styles.body}>
      {title ? <p className={styles.title}>{title}</p> : null}
      {children ? <div className={styles.text}>{children}</div> : null}
    </div>
    {action ? <div className={styles.action}>{action}</div> : null}
  </div>;
}
