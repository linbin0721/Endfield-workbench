import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAppTranslation } from "./i18n";
import { isMobileLikeDevice } from "./device";
import { ScreenCaptureError, captureGameWindow, isScreenCaptureSupported, type ScreenCaptureFailure } from "./screenCapture";

type Crop = { left: number; top: number; width: number; height: number };
type ImageInfo = { file: File; width: number; height: number; url: string };
export type ImageSelection = { blob: Blob; filename: string };
const initialCrop: Crop = { left: 0, top: 0, width: 100, height: 100 };
const allowed = new Set(["image/png", "image/jpeg", "image/webp"]);
const maxBytes = 12 * 1024 * 1024;
const maxPixels = 20_000_000;
const isFullCrop = (crop: Crop) => crop.left === 0 && crop.top === 0 && crop.width === 100 && crop.height === 100;

/** Capture failures are stored as message keys so the active language renders them. */
const captureMessageKeys: Record<ScreenCaptureFailure, string> = {
  unsupported: "image.errorCaptureUnsupported",
  pending: "image.errorCapturePending",
  denied: "image.errorCaptureDenied",
  unavailable: "image.errorCaptureUnavailable",
  "no-frame": "image.errorCaptureNoFrame",
  ended: "image.errorCaptureEnded",
  "too-many-pixels": "image.errorCaptureTooManyPixels",
  "too-large": "image.errorCaptureTooLarge",
  "encode-failed": "image.errorCaptureEncodeFailed",
  aborted: "",
  failed: "image.errorCaptureFailed",
};

function captureErrorKey(error: unknown): string {
  return error instanceof ScreenCaptureError ? captureMessageKeys[error.code] : "image.errorCaptureFailed";
}

type Props = {
  onChanged: (selection: ImageSelection | null, changed?: boolean) => void;
  /** Localized crop hint shown while a manual crop is active. */
  cropHint?: string;
};

export default function ImageInput({ onChanged, cropHint }: Props) {
  const { t } = useAppTranslation("common");
  const [image, setImage] = useState<ImageInfo | null>(null);
  const [crop, setCrop] = useState<Crop>(initialCrop);
  const [useCrop, setUseCrop] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [errorKey, setErrorKey] = useState("");
  const [dragging, setDragging] = useState(false);
  const [captureStatusKey, setCaptureStatusKey] = useState("");
  const originalUrl = useRef<string | null>(null);
  const cropUrl = useRef<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const selection = useRef(0);
  const previewVersion = useRef(0);
  const captureAttempt = useRef(0);
  const captureController = useRef<AbortController | null>(null);
  const isMobile = useMemo(isMobileLikeDevice, []);
  const captureSupported = useMemo(isScreenCaptureSupported, []);
  const capturing = captureStatusKey !== "";

  const release = useCallback(() => {
    if (originalUrl.current) URL.revokeObjectURL(originalUrl.current);
    if (cropUrl.current) URL.revokeObjectURL(cropUrl.current);
    originalUrl.current = null;
    cropUrl.current = null;
  }, []);

  const stopCapture = useCallback(() => {
    captureAttempt.current++;
    captureController.current?.abort();
    captureController.current = null;
  }, []);

  useEffect(() => () => { selection.current++; stopCapture(); release(); }, [release, stopCapture]);

  const clear = useCallback(() => {
    stopCapture();
    setCaptureStatusKey("");
    selection.current++; previewVersion.current++;
    release();
    setImage(null); setPreview(null); setPreparing(false); setCrop(initialCrop); setUseCrop(false); setErrorKey("");
    if (fileInput.current) fileInput.current.value = "";
    onChanged(null);
  }, [onChanged, release, stopCapture]);

  const choose = useCallback(async (file?: File) => {
    if (!file) return;
    stopCapture();
    setCaptureStatusKey("");
    const chosen = ++selection.current;
    previewVersion.current++;
    release(); setImage(null); setPreview(null); setPreparing(false); setCrop(initialCrop); setUseCrop(false);
    onChanged(null);
    if (!allowed.has(file.type)) { setErrorKey("image.errorType"); return; }
    if (file.size > maxBytes) { setErrorKey("image.errorSize"); return; }
    try {
      const bitmap = await createImageBitmap(file);
      const width = bitmap.width, height = bitmap.height;
      bitmap.close();
      if (chosen !== selection.current) return;
      if (width * height > maxPixels) { setErrorKey("image.errorPixels"); return; }
      const url = URL.createObjectURL(file);
      originalUrl.current = url;
      setImage({ file, width, height, url });
      setPreview(null); setPreparing(false); setCrop(initialCrop); setErrorKey("");
      onChanged({ blob: file, filename: file.name || "image.jpg" }, false);
    } catch { if (chosen === selection.current) setErrorKey("image.errorDecode"); }
  }, [onChanged, release, stopCapture]);

  const startCapture = useCallback(() => {
    if (!captureSupported || captureController.current) return;
    const attempt = ++captureAttempt.current;
    const controller = new AbortController();
    captureController.current = controller;
    setErrorKey("");
    setCaptureStatusKey("image.captureSelecting");
    void (async () => {
      try {
        const file = await captureGameWindow(controller.signal, () => {
          if (attempt === captureAttempt.current && !controller.signal.aborted) setCaptureStatusKey("image.captureReading");
        });
        if (attempt !== captureAttempt.current || controller.signal.aborted) return;
        setCaptureStatusKey("");
        await choose(file);
      } catch (failure) {
        if (attempt !== captureAttempt.current || controller.signal.aborted) return;
        setCaptureStatusKey("");
        setErrorKey(captureErrorKey(failure));
      } finally {
        if (captureController.current === controller) captureController.current = null;
        if (attempt === captureAttempt.current) setCaptureStatusKey("");
      }
    })();
  }, [captureSupported, choose]);

  const cancelCapture = useCallback(() => {
    stopCapture();
    setCaptureStatusKey("");
  }, [stopCapture]);

  useEffect(() => {
    const onPaste = (event: ClipboardEvent) => {
      const file = Array.from(event.clipboardData?.files || []).find((item) => item.type.startsWith("image/"));
      if (file) { event.preventDefault(); void choose(file); }
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [choose]);

  useEffect(() => {
    if (!image || !useCrop || isFullCrop(crop)) return;
    let cancelled = false;
    const version = ++previewVersion.current;
    let generatedUrl: string | null = null;
    setPreparing(true);
    setPreview(null);
    if (cropUrl.current) { URL.revokeObjectURL(cropUrl.current); cropUrl.current = null; }
    void (async () => {
      try {
        const bitmap = await createImageBitmap(image.file);
        if (cancelled || version !== previewVersion.current) { bitmap.close(); return; }
        const sx = Math.floor(bitmap.width * crop.left / 100);
        const sy = Math.floor(bitmap.height * crop.top / 100);
        const width = Math.max(1, Math.floor(bitmap.width * crop.width / 100));
        const height = Math.max(1, Math.floor(bitmap.height * crop.height / 100));
        const canvas = document.createElement("canvas");
        canvas.width = width; canvas.height = height;
        canvas.getContext("2d")?.drawImage(bitmap, sx, sy, width, height, 0, 0, width, height);
        bitmap.close();
        const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
        if (cancelled || version !== previewVersion.current) return;
        if (!blob) throw new Error("Cannot generate cropped image");
        const url = URL.createObjectURL(blob);
        generatedUrl = url;
        cropUrl.current = url;
        setPreview(url);
        setPreparing(false);
        if (blob.size > maxBytes) setErrorKey("image.errorCropSize");
        else { setErrorKey(""); onChanged({ blob, filename: "crop.png" }, false); }
      } catch { if (!cancelled && version === previewVersion.current) { setPreparing(false); setErrorKey("image.errorCropPreview"); } }
    })();
    return () => {
      cancelled = true;
      if (previewVersion.current === version) previewVersion.current++;
      if (generatedUrl) URL.revokeObjectURL(generatedUrl);
      if (cropUrl.current === generatedUrl) cropUrl.current = null;
    };
  }, [image, crop, useCrop, onChanged]);

  const selectCrop = (enabled: boolean) => {
    previewVersion.current++;
    setUseCrop(enabled);
    setPreparing(enabled && !isFullCrop(crop));
    setPreview(null);
    setErrorKey("");
    onChanged(enabled && !isFullCrop(crop) ? null : image ? { blob: image.file, filename: image.file.name || "image.jpg" } : null);
  };

  const changeCrop = (field: keyof Crop, value: number) => {
    previewVersion.current++;
    const next = { ...crop, [field]: Number.isFinite(value) ? value : 0 };
    next.left = Math.max(0, Math.min(99, next.left));
    next.top = Math.max(0, Math.min(99, next.top));
    next.width = Math.max(1, Math.min(100 - next.left, next.width));
    next.height = Math.max(1, Math.min(100 - next.top, next.height));
    setCrop(next);
    setPreparing(!isFullCrop(next));
    setPreview(null);
    setErrorKey("");
    onChanged(!isFullCrop(next) ? null : image ? { blob: image.file, filename: image.file.name || "image.jpg" } : null);
  };

  const cropped = useCrop && !isFullCrop(crop);
  const uploadWidth = image && cropped ? Math.max(1, Math.floor(image.width * crop.width / 100)) : image?.width;
  const uploadHeight = image && cropped ? Math.max(1, Math.floor(image.height * crop.height / 100)) : image?.height;
  // Desktop with capture support makes the window screenshot the primary action;
  // mobile and capture-less desktops keep the file picker primary.
  const choosePrimary = isMobile || !captureSupported;
  const chooseLabelKey = image ? "image.chooseOther" : isMobile ? "image.chooseFromAlbum" : "image.chooseFile";
  const cropLabels: Record<keyof Crop, string> = {
    left: t("image.cropLeft"), top: t("image.cropTop"),
    width: t("image.cropWidth"), height: t("image.cropHeight"),
  };
  const error = errorKey ? t(errorKey) : "";

  return <section className={`panel ${isMobile ? "image-input-mobile" : "image-input-desktop"}`} aria-labelledby="image-title">
    <div className="section-heading"><div><span className="eyebrow">{t("image.eyebrow")}</span><h2 id="image-title">{t("image.title")}</h2></div><span className="badge">{t("image.localOnlyBadge")}</span></div>
    <p className="muted">{isMobile ? t("image.introMobile") : t("image.introDesktop")}{t("image.uploadNote")}</p>
    <div className={`dropzone ${dragging ? "dragging" : ""}`} onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); void choose(event.dataTransfer.files[0]); }}>
      <input ref={fileInput} type="file" accept="image/png,image/jpeg,image/webp" id="image-file" hidden tabIndex={-1} aria-label={t("image.fileInputLabel")}
        onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; void choose(file); }} />
      <div className="dropzone-actions">
        <button type="button" className={`button ${choosePrimary ? "primary" : "secondary"}`} onClick={() => fileInput.current?.click()}>{t(chooseLabelKey)}</button>
        {!isMobile && <button type="button" className={`button ${captureSupported ? "primary" : "secondary"}`} disabled={!captureSupported || capturing} onClick={startCapture}>{t("image.captureWindow")}</button>}
      </div>
      {!isMobile && <span className="dropzone-note">{t("image.dropNote")}</span>}
      <small>{t("image.limits")}</small>
    </div>
    {!isMobile && !captureSupported && <p className="muted small capture-hint">{t("image.captureUnsupported")}</p>}
    {capturing && <div className="capture-status" role="status"><span>{t(captureStatusKey)}</span>
      <button className="text-button" type="button" onClick={cancelCapture}>{t("image.captureCancel")}</button></div>}
    {error && <p role="alert" className="error-text">{error}</p>}
    {image && <>
      <div className="image-meta"><span>{t("image.meta", { name: image.file.name, width: image.width, height: image.height })}</span><button className="text-button" type="button" onClick={clear}>{t("image.clear")}</button></div>
      <fieldset className="image-source"><legend>{t("image.scopeLegend")}</legend>
        <label><input type="radio" name="image-source" checked={!useCrop} onChange={() => selectCrop(false)} /> {t("image.scopeFull")}</label>
        <label><input type="radio" name="image-source" checked={useCrop} onChange={() => selectCrop(true)} /> {t("image.scopeCrop")}</label>
      </fieldset>
      <p className="muted">{!useCrop ? t("image.fullNote") : cropped
        ? cropHint ?? t("image.cropNoteDefault") : t("image.cropFullNote")}</p>
      {useCrop && <fieldset className="crop-controls"><legend>{t("image.cropLegend")}</legend>
        {(["left", "top", "width", "height"] as const).map((field) => <label key={field}>
          {cropLabels[field]}
          <input type="number" inputMode="numeric" min={field === "width" || field === "height" ? 1 : 0} max="100"
            value={crop[field]} onChange={(event) => changeCrop(field, Number(event.target.value))} /> %
        </label>)}
      </fieldset>}
      <div className="image-previews single"><figure><figcaption>{t("image.uploadCaption", {
        width: uploadWidth ?? 0, height: uploadHeight ?? 0,
        suffix: cropped ? t("image.uploadCropped") : t("image.uploadFull") })}</figcaption>
        {cropped && (preparing || !preview) ? <span className="muted" role="status">{t("image.preparingCrop")}</span> : <img src={cropped ? preview! : image.url} alt={t("image.previewAlt")} />}
      </figure></div>
    </>}
  </section>;
}
