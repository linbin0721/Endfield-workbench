import { useEffect, useState } from "react";
import { Button } from "../src/ui/Button/Button";
import { Dialog } from "../src/ui/Dialog/Dialog";
import { CaptureIcon, ImageIcon, RefreshIcon, SearchIcon, WarningIcon } from "../src/ui/icons";
import { ItemCard, type Rarity } from "../src/ui/ItemCard/ItemCard";
import { Notice } from "../src/ui/Notice/Notice";
import { PageHeader } from "../src/ui/PageHeader/PageHeader";
import { Panel } from "../src/ui/Panel/Panel";
import { SectionTitle } from "../src/ui/SectionTitle/SectionTitle";
import { SegmentedControl } from "../src/ui/SegmentedControl/SegmentedControl";
import { Select } from "../src/ui/Select/Select";
import { SuccessGlow, SuccessReveal } from "../src/ui/SuccessReveal/SuccessReveal";
import { ThemeToggle } from "../src/ui/ThemeToggle/ThemeToggle";
import { Toast } from "../src/ui/Toast/Toast";
import { COPY, LOCALES, LOCALE_LABELS, type Locale } from "./copy";
import styles from "./preview.module.css";

// Demo board: 0 empty, 1 blocked, 2+ balloon lift.
const BOARD = [
  [0, 1, 0, 0, 0],
  [0, 2, 0, 1, 0],
  [0, 0, 0, 2, 0],
  [1, 2, 0, 0, 0],
  [0, 0, 0, 1, 0],
];

const ITEMS: { name: string; rarity: Rarity; level: number; shape: "hex" | "diamond" | "ring" }[] = [
  { name: "Operator A", rarity: 6, level: 90, shape: "hex" },
  { name: "Operator B", rarity: 5, level: 80, shape: "hex" },
  { name: "Weapon C", rarity: 4, level: 60, shape: "diamond" },
  { name: "Gear D", rarity: 3, level: 40, shape: "ring" },
];

function Placeholder({ shape }: { shape: "hex" | "diamond" | "ring" }) {
  // Neutral shapes only; real icons come from the app's own media pipeline.
  return <svg viewBox="0 0 40 40" width="60%" height="60%" aria-hidden="true">
    {shape === "hex" ? <path d="M20 4l14 8v16l-14 8-14-8V12z" fill="none" stroke="currentColor" strokeWidth="2" /> : null}
    {shape === "diamond" ? <path d="M20 4l16 16-16 16L4 20z" fill="none" stroke="currentColor" strokeWidth="2" /> : null}
    {shape === "ring" ? <circle cx="20" cy="20" r="14" fill="none" stroke="currentColor" strokeWidth="2" /> : null}
  </svg>;
}

export function DesignPreview() {
  const [locale, setLocale] = useState<Locale>("zh-CN");
  const t = COPY[locale];
  const [mode, setMode] = useState("");
  const [quality, setQuality] = useState("mid");
  const [level, setLevel] = useState("90");
  const [potential, setPotential] = useState("any");
  const [selectedItem, setSelectedItem] = useState(0);
  const [solveCount, setSolveCount] = useState(1);
  const [toastOpen, setToastOpen] = useState(false);

  useEffect(() => { document.documentElement.lang = locale; }, [locale]);

  const qualityOptions = [
    { value: "custom", label: "Custom" },
    { value: "ultra", label: "Ultra", adornment: <WarningIcon /> },
    { value: "high", label: "High" },
    { value: "mid", label: "Medium" },
    { value: "low", label: "Low" },
    { value: "off", label: "Off", disabled: true },
  ];
  const levelOptions = ["1", "20", "40", "60", "80", "90"].map((value) => ({ value, label: `LV.${value}` }));

  return <div className={styles.page}>
    <header className={styles.topbar}>
      <p className={styles.brand}><span className={styles.brandMark} aria-hidden="true" />{t.brand}</p>
      <span className={styles.badge}>{t.badge}</span>
      <ThemeToggle toDarkLabel={t.themeToDark} toLightLabel={t.themeToLight} />
      <SegmentedControl
        aria-label={t.language}
        size="sm"
        value={locale}
        onValueChange={(value) => setLocale(value as Locale)}
        segments={LOCALES.map((code) => ({ value: code, label: <span lang={code}>{LOCALE_LABELS[code]}</span> }))}
      />
    </header>

    <main>
      <section className={styles.band} aria-label={t.puzzleBand}>
        <div className={styles.inner}>
          <p className={styles.bandLabel}>{t.puzzleBand}</p>
          <PageHeader eyebrow={t.puzzleEyebrow} title={t.puzzleTitle}><p>{t.puzzleIntro}</p></PageHeader>

          <div className={styles.grid}>
            <Panel corners>
              <SectionTitle>{t.inputTitle}</SectionTitle>
              <div className={styles.stack}>
                <SegmentedControl
                  aria-label={t.mode}
                  block
                  value={mode}
                  onValueChange={setMode}
                  segments={[{ value: "screenshot", label: t.modeScreenshot }, { value: "code", label: t.modeCode }]}
                />
                <p className={styles.hint}>{t.modeHint}</p>
                <div className={styles.buttons}>
                  <Button icon={<ImageIcon />}>{t.choose}</Button>
                  <Button icon={<CaptureIcon />}>{t.capture}</Button>
                  <Button variant="secondary" size="sm">{t.clear}</Button>
                </div>
                <div className={styles.buttons}>
                  <Button variant="accent" block>{t.solve}</Button>
                  <Button disabled block>{t.solve}</Button>
                </div>
              </div>
            </Panel>

            <Panel>
              <SectionTitle aside={<Button variant="ghost" size="sm" onClick={() => setSolveCount((n) => n + 1)}>{t.replay}</Button>}>
                {t.resultTitle}
              </SectionTitle>
              <div className={styles.boardArea}>
                <SuccessReveal key={`reveal-${solveCount}`} title={t.solved} detail={t.solvedDetail} />
                <SuccessGlow playKey={solveCount}>
                  <div className={styles.board} role="img" aria-label={t.resultTitle}>
                    {BOARD.flatMap((row, r) => row.map((cell, c) => <span
                      key={`${r}-${c}`}
                      className={[styles.cell, cell === 1 ? styles.blocked : "", cell >= 2 ? styles.filled : ""].join(" ")}
                    >{cell >= 2 ? cell : ""}</span>))}
                  </div>
                </SuccessGlow>
                <div className={styles.buttons}>
                  <Button variant="secondary" size="sm" onClick={() => setToastOpen(true)}>{t.toastButton}</Button>
                  <Dialog
                    trigger={<Button variant="secondary" size="sm">{t.dialogButton}</Button>}
                    title={t.dialogTitle}
                    description={t.dialogDescription}
                    closeLabel={t.close}
                    footer={<>
                      <Dialog.CloseButton variant="secondary">{t.cancel}</Dialog.CloseButton>
                      <Dialog.CloseButton variant="accent" icon={<RefreshIcon />}>{t.confirm}</Dialog.CloseButton>
                    </>}
                  >
                    <p className={styles.body}>{t.dialogBody}</p>
                    <label className={styles.field}>
                      <span>Quality</span>
                      <Select aria-label="Quality" value={quality} onValueChange={setQuality} options={qualityOptions} />
                    </label>
                  </Dialog>
                </div>
              </div>
            </Panel>

            <Panel>
              <SectionTitle level={3}>Notice</SectionTitle>
              <div className={styles.stack}>
                <Notice title={t.noticeInfoTitle}>{t.noticeInfoText}</Notice>
                <Notice tone="success" title={t.noticeSuccess} />
                <Notice tone="warning" title={t.noticeWarningTitle}>{t.noticeWarningText}</Notice>
                <Notice
                  tone="danger"
                  title={t.noticeDangerTitle}
                  action={<Button variant="secondary" size="sm" icon={<RefreshIcon />}>{t.retry}</Button>}
                >{t.noticeDangerText}</Notice>
              </div>
            </Panel>

            <Panel>
              <SectionTitle level={3}>{t.typeTitle}</SectionTitle>
              <p className={styles.bigNumber}>90<span>/90</span></p>
              <p className={styles.body}>{t.typeSample}</p>
              <p className={styles.muted}>{t.longText}</p>
              <p className={styles.mono}>WL-A2014 · V40005 · 1440 × 900</p>
            </Panel>
          </div>
        </div>
      </section>

      <section className={`${styles.band} ${styles.secondBand}`} aria-label={t.calcBand}>
        <div className={styles.inner}>
          <p className={styles.bandLabel}>{t.calcBand}</p>
          <PageHeader eyebrow={t.calcEyebrow} title={t.calcTitle}><p>{t.calcIntro}</p></PageHeader>

          <div className={styles.grid}>
            <Panel corners tone="strong">
              <SectionTitle>{t.operatorTitle}</SectionTitle>
              <div className={styles.stack}>
                <label className={styles.field}>
                  <span>{t.level}</span>
                  <Select aria-label={t.level} value={level} onValueChange={setLevel} options={levelOptions} />
                </label>
                <div className={styles.field}>
                  <span>{t.potential}</span>
                  <SegmentedControl
                    aria-label={t.potential}
                    block
                    value={potential}
                    onValueChange={setPotential}
                    segments={[{ value: "fixed", label: t.potentialFixed }, { value: "any", label: t.potentialAny }]}
                  />
                </div>
                <div className={styles.buttons}>
                  <Button variant="accent" block icon={<SearchIcon />}>{t.search}</Button>
                  <Button disabled block>{t.search}</Button>
                </div>
              </div>
            </Panel>

            <Panel tone="strong">
              <SectionTitle>{t.statsTitle}</SectionTitle>
              <dl className={styles.stats}>
                {t.stats.map((label, index) => <div key={label} className={styles.statRow}>
                  <dt>{label}</dt>
                  <dd><span className={styles.statValue}>{[97, 174, 99, 119][index]}</span>
                    {index === 0 ? <span className={styles.statGain}>+10</span> : null}</dd>
                </div>)}
              </dl>
            </Panel>

            <Panel tone="strong">
              <SectionTitle aside={`${ITEMS.length}`}>{t.itemsTitle}</SectionTitle>
              <div className={styles.items}>
                {ITEMS.map((item, index) => <ItemCard
                  key={item.name}
                  name={item.name}
                  rarity={item.rarity}
                  level={item.level}
                  image={<Placeholder shape={item.shape} />}
                  selected={selectedItem === index}
                  onSelect={() => setSelectedItem(index)}
                />)}
              </div>
              <div className={styles.buttons}>
                <Button size="sm">{t.choose}</Button>
                <Dialog
                  trigger={<Button variant="secondary" size="sm">{t.dialogButton}</Button>}
                  title={t.dialogTitle}
                  description={t.dialogDescription}
                  closeLabel={t.close}
                  footer={<Dialog.CloseButton variant="accent">{t.confirm}</Dialog.CloseButton>}
                />
              </div>
            </Panel>

            <Panel tone="strong">
              <SectionTitle level={3}>{t.colorTitle}</SectionTitle>
              <p className={styles.body}>{t.focusHint}</p>
              <Notice tone="warning" title={t.noticeWarningTitle}>{t.noticeWarningText}</Notice>
            </Panel>
          </div>
        </div>
      </section>
    </main>

    <footer className={styles.footer}>{t.footer}</footer>
    <Toast open={toastOpen} onOpenChange={setToastOpen}>{t.toast}</Toast>
  </div>;
}
