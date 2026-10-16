import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { isMobileLikeDevice } from "../../device";
import { ScreenCaptureError, captureGameWindow, isScreenCaptureSupported, type ScreenCaptureFailure } from "../../screenCapture";

/** Crop rectangle in percent of the original image. */
export type Crop = { left: number; top: number; width: number; height: number };
export type ImageInfo = { file: File; width: number; height: number; url: string };
/** What would be uploaded right now; null while nothing valid is ready. */
export type ImageSelection = { blob: Blob; filename: string };

export const FULL_CROP: Crop = { left: 0, top: 0, width: 100, height: 100 };
const ALLOWED = new Set(["image/png", "image/jpeg", "image/webp"]);
const MAX_BYTES = 12 * 1024 * 1024;
const MAX_PIXELS = 20_000_000;
/** Dragging the crop box re-renders the PNG only after it settles. */
const CROP_DEBOUNCE_MS = 220;

export const isFullCrop = (crop: Crop) => crop.left <= 0 && crop.top <= 0 && crop.width >= 100 && crop.height >= 100;

/** Keeps a crop inside the image with at least 1% on each side. */
export function clampCrop(crop: Crop): Crop {
  const round = (value: number) => Math.round(value * 10) / 10;
  const left = Math.max(0, Math.min(99, round(crop.left)));
  const top = Math.max(0, Math.min(99, round(crop.top)));
  return {
    left,
    top,
    width: Math.max(1, Math.min(100 - left, round(crop.width))),
    height: Math.max(1, Math.min(100 - top, round(crop.height))),
  };
}

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

const captureErrorKey = (error: unknown) =>
  error instanceof ScreenCaptureError ? captureMessageKeys[error.code] : "image.errorCaptureFailed";

/**
 * Image import shared by the puzzle workbenches: file choice, drop, paste and
 * a single-frame window capture, validation (type, 12 MB, 20 MP), an optional
 * crop rendered to PNG, and the release of every object URL. Errors are
 * message keys in the `common` namespace. `onSelection(selection, isNew)`
 * reports the upload candidate; `isNew` means the previous image is gone and
 * the page should drop its tasks and results.
 */
export function useImageSource(onSelection: (selection: ImageSelection | null, isNew: boolean) => void) {
  const [image, setImage] = useState<ImageInfo | null>(null);
  const [crop, setCropState] = useState<Crop>(FULL_CROP);
  const [cropping, setCropping] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [errorKey, setErrorKey] = useState("");
  const [captureStatusKey, setCaptureStatusKey] = useState("");
  const originalUrl = useRef<string | null>(null);
  const cropUrl = useRef<string | null>(null);
  const selectionVersion = useRef(0);
  const previewVersion = useRef(0);
  const captureAttempt = useRef(0);
  const captureController = useRef<AbortController | null>(null);
  const report = useRef(onSelection);
  report.current = onSelection;
  const isMobile = useMemo(isMobileLikeDevice, []);
  const captureSupported = useMemo(isScreenCaptureSupported, []);

  const release = useCallback(() => {
    if (originalUrl.current) URL.revokeObjectURL(originalUrl.current);
    if (cropUrl.current) URL.revokeObjectURL(cropUrl.current);
    originalUrl.current = null;
    cropUrl.current = null;
  }, []);

  const stopCapture = useCallback(() => {
    captureAttempt.current += 1;
    captureController.current?.abort();
    captureController.current = null;
  }, []);

  useEffect(() => () => { selectionVersion.current += 1; stopCapture(); release(); }, [release, stopCapture]);

  const clear = useCallback(() => {
    stopCapture();
    setCaptureStatusKey("");
    selectionVersion.current += 1;
    previewVersion.current += 1;
    release();
    setImage(null); setPreview(null); setPreparing(false); setCropState(FULL_CROP); setCropping(false); setErrorKey("");
    report.current(null, true);
  }, [release, stopCapture]);

  const choose = useCallback(async (file?: File | null) => {
    if (!file) return;
    stopCapture();
    setCaptureStatusKey("");
    const chosen = ++selectionVersion.current;
    previewVersion.current += 1;
    release();
    setImage(null); setPreview(null); setPreparing(false); setCropState(FULL_CROP); setCropping(false);
    report.current(null, true);
    if (!ALLOWED.has(file.type)) { setErrorKey("image.errorType"); return; }
    if (file.size > MAX_BYTES) { setErrorKey("image.errorSize"); return; }
    try {
      const bitmap = await createImageBitmap(file);
      const width = bitmap.width, height = bitmap.height;
      bitmap.close();
      if (chosen !== selectionVersion.current) return;
      if (width * height > MAX_PIXELS) { setErrorKey("image.errorPixels"); return; }
      const url = URL.createObjectURL(file);
      originalUrl.current = url;
      setImage({ file, width, height, url });
      setErrorKey("");
      report.current({ blob: file, filename: file.name || "image.jpg" }, false);
    } catch {
      if (chosen === selectionVersion.current) setErrorKey("image.errorDecode");
    }
  }, [release, stopCapture]);

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

  const cancelCapture = useCallback(() => { stopCapture(); setCaptureStatusKey(""); }, [stopCapture]);

  // Paste anywhere on the page.
  useEffect(() => {
    const onPaste = (event: ClipboardEvent) => {
      const file = Array.from(event.clipboardData?.files || []).find((item) => item.type.startsWith("image/"));
      if (file) { event.preventDefault(); void choose(file); }
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [choose]);

  const cropped = cropping && !isFullCrop(crop);

  // Render the crop to a PNG once the box settles; the full image is the selection otherwise.
  useEffect(() => {
    if (!image || !cropped) return;
    let cancelled = false;
    let generatedUrl: string | null = null;
    const version = ++previewVersion.current;
    setPreparing(true);
    const timer = window.setTimeout(() => {
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
          if (cropUrl.current) URL.revokeObjectURL(cropUrl.current);
          const url = URL.createObjectURL(blob);
          generatedUrl = url;
          cropUrl.current = url;
          setPreview(url);
          setPreparing(false);
          if (blob.size > MAX_BYTES) setErrorKey("image.errorCropSize");
          else { setErrorKey(""); report.current({ blob, filename: "crop.png" }, false); }
        } catch {
          if (!cancelled && version === previewVersion.current) { setPreparing(false); setErrorKey("image.errorCropPreview"); }
        }
      })();
    }, CROP_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      if (previewVersion.current === version) previewVersion.current += 1;
      if (generatedUrl && cropUrl.current === generatedUrl) { URL.revokeObjectURL(generatedUrl); cropUrl.current = null; }
    };
  }, [image, crop, cropped]);

  /** Switches between the whole image and the crop box; the upload candidate follows. */
  const setCropMode = useCallback((enabled: boolean) => {
    previewVersion.current += 1;
    setCropping(enabled);
    setPreview(null);
    setErrorKey("");
    const willCrop = enabled && !isFullCrop(crop);
    setPreparing(willCrop);
    report.current(willCrop ? null : image ? { blob: image.file, filename: image.file.name || "image.jpg" } : null, false);
  }, [crop, image]);

  const setCrop = useCallback((next: Crop) => {
    const value = clampCrop(next);
    previewVersion.current += 1;
    setCropState(value);
    setPreview(null);
    setErrorKey("");
    const willCrop = cropping && !isFullCrop(value);
    setPreparing(willCrop);
    report.current(willCrop ? null : image ? { blob: image.file, filename: image.file.name || "image.jpg" } : null, false);
  }, [cropping, image]);

  const uploadSize = image
    ? cropped
      ? { width: Math.max(1, Math.floor(image.width * crop.width / 100)), height: Math.max(1, Math.floor(image.height * crop.height / 100)) }
      : { width: image.width, height: image.height }
    : null;

  return {
    image, crop, cropping, cropped, preview, preparing, errorKey, uploadSize,
    captureStatusKey, capturing: captureStatusKey !== "", captureSupported, isMobile,
    choose, clear, startCapture, cancelCapture, setCropMode, setCrop,
  };
}

export type ImageSource = ReturnType<typeof useImageSource>;
