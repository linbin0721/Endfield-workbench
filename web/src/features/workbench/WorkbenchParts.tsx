import type { ReactNode } from "react";
import type { Capability } from "../../api";
import { useAppTranslation, useMessages } from "../../i18n";
import { Button } from "../../ui/Button/Button";
import { PageHeader } from "../../ui/PageHeader/PageHeader";
import { HelpButton } from "./HelpButton";
import { StepBar } from "./StepBar";
import type { useServiceCapabilities } from "./useServiceCapabilities";
import s from "./workbench.module.css";

type Service = ReturnType<typeof useServiceCapabilities>;

/** Page title, service status, the help panel button and the three-step bar. */
export function WorkbenchHeader({ eyebrow, title, intro, step, service, capability, capabilityMissing, help }: {
  eyebrow: string;
  title: string;
  intro: string;
  step: number;
  service: Service;
  capability: Capability | undefined;
  capabilityMissing: string;
  help: ReactNode;
}) {
  const { t } = useAppTranslation("common");
  const { render } = useMessages();
  const state = service.state === "ready" && !capability ? "missing" : service.state;
  const text = service.state === "loading" ? t("service.querying")
    : service.state === "error" ? t("service.unavailable", { message: render(service.error, "error") })
      : capability ? t("service.status", {
        solving: t(capability.solving_available ? "service.solvingAvailable" : "service.solvingUnavailable"),
        recognition: t(capability.recognition_available ? "service.recognitionAvailable" : "service.recognitionUnavailable"),
      }) : capabilityMissing;
  return <header className={s.header}>
    <div className={s.headerTop}>
      <PageHeader eyebrow={eyebrow} title={title}>{intro}</PageHeader>
      <div className={s.headerSide}>
        <HelpButton label={t("workbench.help")} title={t("workbench.helpTitle")} closeLabel={t("workbench.helpClose")}>{help}</HelpButton>
        <div className={s.service} role="status" aria-live="polite" data-service={state}>
          <span className={s.dot} aria-hidden="true" />
          <span className={s.serviceText}>{text}</span>
          {service.state === "error" && <Button variant="ghost" size="sm" onClick={() => void service.refresh()}>{t("service.retry")}</Button>}
        </div>
      </div>
    </div>
    <StepBar label={t("workbench.stepsLabel")} current={step} steps={[
      { key: "import", label: t("workbench.stepImport") },
      { key: "puzzle", label: t("workbench.stepPuzzle") },
      { key: "answer", label: t("workbench.stepAnswer") },
    ]} />
  </header>;
}

/** Placeholder of an empty or busy step, on the board grid pattern. */
export function WaitingState({ text, busy = false, children }: { text: string; busy?: boolean; children?: ReactNode }) {
  return <div className={s.waiting} data-busy={busy || undefined}>
    {busy && <span className={s.scan} aria-hidden="true" />}
    <p className={s.waitingText} role={busy ? "status" : undefined}>{text}</p>
    {children}
  </div>;
}

/** Scrolls an element into view only when its top is below most of the viewport (stacked phone layout). */
export function revealIfHidden(element: HTMLElement | null) {
  if (!element) return;
  const top = element.getBoundingClientRect().top;
  if (top < window.innerHeight * 0.8) return;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  element.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
}
