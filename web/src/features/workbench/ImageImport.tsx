import { useRef, useState, type DragEvent } from "react";
import { useAppTranslation } from "../../i18n";
import { Button } from "../../ui/Button/Button";
import { CaptureIcon, CloseIcon, ImageIcon } from "../../ui/icons";
import { SegmentedControl } from "../../ui/SegmentedControl/SegmentedControl";
import { CropBox } from "./CropBox";
import type { ImageSource } from "./useImageSource";
import s from "./workbench.module.css";

/**
 * Screenshot import: an empty drop zone (choose, capture on desktop, drop,
 * paste), then the chosen image with a whole-image / crop switch and a
 * draggable crop box. Upload happens elsewhere, only on the page's action.
 */
export function ImageImport({ source, cropHint }: { source: ImageSource; cropHint: string }) {
  const { t } = useAppTranslation("common");
  const fileInput = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const { image, isMobile, captureSupported, capturing } = source;
  const chooseKey = image ? "image.chooseOther" : isMobile ? "image.chooseFromAlbum" : "image.chooseFile";
  const error = source.errorKey ? t(source.errorKey) : "";

  const dropHandlers = {
    onDragOver: (event: DragEvent) => { event.preventDefault(); setDragging(true); },
    onDragLeave: () => setDragging(false),
    onDrop: (event: DragEvent) => { event.preventDefault(); setDragging(false); void source.choose(event.dataTransfer.files[0]); },
  };
  const actions = <div className={s.importActions}>
    <Button variant={isMobile || !captureSupported ? "primary" : "secondary"} size={image ? "sm" : "md"} icon={<ImageIcon />}
      onClick={() => fileInput.current?.click()}>{t(chooseKey)}</Button>
    {!isMobile && <Button variant={captureSupported && !image ? "primary" : "secondary"} size={image ? "sm" : "md"} icon={<CaptureIcon />}
      disabled={!captureSupported || capturing} onClick={source.startCapture}>{t("image.captureWindow")}</Button>}
  </div>;

  return <div className={s.import} data-mobile={isMobile || undefined}>
    <input ref={fileInput} type="file" accept="image/png,image/jpeg,image/webp" id="image-file" hidden tabIndex={-1}
      aria-label={t("image.fileInputLabel")}
      onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; void source.choose(file); }} />
    {!image
      ? <div className={s.dropzone} data-dragging={dragging || undefined} {...dropHandlers}>
        <span className={s.dropIcon} aria-hidden="true"><ImageIcon /></span>
        <p className={s.dropTitle}>{isMobile ? t("image.introMobile") : t("image.introDesktop")}</p>
        {actions}
        {!isMobile && <p className={s.dropNote}>{t("image.dropNote")}</p>}
        <p className={s.limits}>{t("image.limits")}</p>
      </div>
      : <div className={s.stage} {...dropHandlers}>
        <div className={s.stageBar}>
          <SegmentedControl size="sm" aria-label={t("image.scopeLegend")} value={source.cropping ? "crop" : "full"}
            onValueChange={(value) => source.setCropMode(value === "crop")}
            segments={[{ value: "full", label: t("workbench.fullImage") }, { value: "crop", label: t("image.scopeCrop") }]} />
          <span className={s.stageMeta}>{t("image.meta", { name: image.file.name, width: image.width, height: image.height })}</span>
        </div>
        <figure className={s.frame}>
          <div className={s.frameInner}>
            <img className={s.image} src={image.url} alt={t("image.previewAlt")} draggable={false} />
            {source.cropping && <CropBox crop={source.crop} onChange={source.setCrop} boxLabel={t("workbench.cropBox")}
              cornerLabels={{ nw: t("workbench.cropCornerNw"), ne: t("workbench.cropCornerNe"), sw: t("workbench.cropCornerSw"), se: t("workbench.cropCornerSe") }} />}
          </div>
          <figcaption className={s.caption}>
            {source.uploadSize && t("image.uploadCaption", {
              width: source.uploadSize.width, height: source.uploadSize.height,
              suffix: source.cropped ? t("image.uploadCropped") : t("image.uploadFull"),
            })}
            {source.cropped && source.preparing && <span role="status"> · {t("image.preparingCrop")}</span>}
          </figcaption>
        </figure>
        {source.cropping && <p className={s.hint}>{source.cropped ? cropHint : t("image.cropFullNote")}</p>}
        <div className={s.stageActions}>
          {actions}
          <Button variant="ghost" size="sm" onClick={source.clear}>{t("image.clear")}</Button>
        </div>
      </div>}
    {!isMobile && !captureSupported && !image && <p className={s.hint}>{t("image.captureUnsupported")}</p>}
    {capturing && <div className={s.capture} role="status">
      <span>{t(source.captureStatusKey)}</span>
      <Button variant="ghost" size="sm" icon={<CloseIcon />} onClick={source.cancelCapture}>{t("image.captureCancel")}</Button>
    </div>}
    {error && <p className={s.error} role="alert">{error}</p>}
  </div>;
}
