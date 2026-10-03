import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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

const captureMessages: Record<ScreenCaptureFailure, string> = {
  unsupported: "当前浏览器或环境不支持窗口截图，请使用“选择图片”、拖放或在页面中粘贴。",
  pending: "窗口截图暂时无法启动，请关闭已有选择框、回到此页面后重试。",
  denied: "未选择窗口或已取消截图，当前图片保持不变。",
  unavailable: "无法读取所选窗口，请确认窗口未被最小化或受保护，然后重试。",
  "no-frame": "没有获取到窗口画面；请选择游戏窗口并保持其可见，然后重试。",
  ended: "窗口共享已结束，未能截取画面；当前图片保持不变。",
  "too-many-pixels": "截取画面超过 2000 万像素，请降低分辨率或改用选图。",
  "too-large": "截取的 PNG 超过 12 MB，请缩小窗口或改用选图。",
  "encode-failed": "无法生成 PNG 截图，请重试或改用选图。",
  aborted: "",
  failed: "截图失败，请重试或改用选图。",
};

function captureErrorMessage(error: unknown): string {
  return error instanceof ScreenCaptureError ? captureMessages[error.code] : "截图失败，请重试或改用选图。";
}

type Props = {
  onChanged: (selection: ImageSelection | null, changed?: boolean) => void;
  cropHint?: string;
};

export default function ImageInput({ onChanged, cropHint }: Props) {
  const [image, setImage] = useState<ImageInfo | null>(null);
  const [crop, setCrop] = useState<Crop>(initialCrop);
  const [useCrop, setUseCrop] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const [captureStatus, setCaptureStatus] = useState("");
  const originalUrl = useRef<string | null>(null);
  const cropUrl = useRef<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const selection = useRef(0);
  const previewVersion = useRef(0);
  const captureAttempt = useRef(0);
  const captureController = useRef<AbortController | null>(null);
  const isMobile = useMemo(isMobileLikeDevice, []);
  const captureSupported = useMemo(isScreenCaptureSupported, []);
  const capturing = captureStatus !== "";

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
    setCaptureStatus("");
    selection.current++; previewVersion.current++;
    release();
    setImage(null); setPreview(null); setPreparing(false); setCrop(initialCrop); setUseCrop(false); setError("");
    if (fileInput.current) fileInput.current.value = "";
    onChanged(null);
  }, [onChanged, release, stopCapture]);

  const choose = useCallback(async (file?: File) => {
    if (!file) return;
    stopCapture();
    setCaptureStatus("");
    const chosen = ++selection.current;
    previewVersion.current++;
    release(); setImage(null); setPreview(null); setPreparing(false); setCrop(initialCrop); setUseCrop(false);
    onChanged(null);
    if (!allowed.has(file.type)) { setError("仅支持 PNG、JPEG 或 WebP 图片。"); return; }
    if (file.size > maxBytes) { setError("图片不能超过 12 MB；请先缩小文件。"); return; }
    try {
      const bitmap = await createImageBitmap(file);
      const width = bitmap.width, height = bitmap.height;
      bitmap.close();
      if (chosen !== selection.current) return;
      if (width * height > maxPixels) { setError("图片像素不能超过 2000 万；请先缩小图片。"); return; }
      const url = URL.createObjectURL(file);
      originalUrl.current = url;
      setImage({ file, width, height, url });
      setPreview(null); setPreparing(false); setCrop(initialCrop); setError("");
      onChanged({ blob: file, filename: file.name || "image.jpg" }, false);
    } catch { if (chosen === selection.current) setError("无法读取这张图片，请换一张清晰的 PNG、JPEG 或 WebP 图片。"); }
  }, [onChanged, release, stopCapture]);

  const startCapture = useCallback(() => {
    if (!captureSupported || captureController.current) return;
    const attempt = ++captureAttempt.current;
    const controller = new AbortController();
    captureController.current = controller;
    setError("");
    setCaptureStatus("请在弹出的选择框中选择游戏窗口…");
    void (async () => {
      try {
        const file = await captureGameWindow(controller.signal, () => {
          if (attempt === captureAttempt.current && !controller.signal.aborted) setCaptureStatus("已选择来源，正在获取窗口画面…");
        });
        if (attempt !== captureAttempt.current || controller.signal.aborted) return;
        setCaptureStatus("");
        await choose(file);
      } catch (failure) {
        if (attempt !== captureAttempt.current || controller.signal.aborted) return;
        setCaptureStatus("");
        setError(captureErrorMessage(failure));
      } finally {
        if (captureController.current === controller) captureController.current = null;
        if (attempt === captureAttempt.current) setCaptureStatus("");
      }
    })();
  }, [captureSupported, choose]);

  const cancelCapture = useCallback(() => {
    stopCapture();
    setCaptureStatus("");
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
        if (blob.size > maxBytes) setError("裁剪后的 PNG 超过 12 MB，请缩小裁剪范围或改用原图。");
        else { setError(""); onChanged({ blob, filename: "crop.png" }, false); }
      } catch { if (!cancelled && version === previewVersion.current) { setPreparing(false); setError("裁剪预览失败，请调整范围或更换图片。"); } }
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
    setError("");
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
    setError("");
    onChanged(!isFullCrop(next) ? null : image ? { blob: image.file, filename: image.file.name || "image.jpg" } : null);
  };

  const cropped = useCrop && !isFullCrop(crop);
  const uploadWidth = image && cropped ? Math.max(1, Math.floor(image.width * crop.width / 100)) : image?.width;
  const uploadHeight = image && cropped ? Math.max(1, Math.floor(image.height * crop.height / 100)) : image?.height;
  // Desktop with capture support makes the window screenshot the primary action;
  // mobile and capture-less desktops keep the file picker primary.
  const choosePrimary = isMobile || !captureSupported;
  const chooseLabel = image ? "更换图片" : isMobile ? "从相册选择" : "选择图片";

  return <section className={`panel ${isMobile ? "image-input-mobile" : "image-input-desktop"}`} aria-labelledby="image-title">
    <div className="section-heading"><div><span className="eyebrow">01 / 图片</span><h2 id="image-title">导入画面</h2></div><span className="badge">图片仅本地预览</span></div>
    <p className="muted">{isMobile ? "先用设备截屏，再从相册选择图片。" : "选择、拖放或粘贴截图，或直接截取游戏窗口。"}只有点击“识别并求解”后才会上传选定范围。</p>
    <div className={`dropzone ${dragging ? "dragging" : ""}`} onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); void choose(event.dataTransfer.files[0]); }}>
      <input ref={fileInput} type="file" accept="image/png,image/jpeg,image/webp" id="image-file" hidden tabIndex={-1} aria-label="选择图片文件"
        onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; void choose(file); }} />
      <div className="dropzone-actions">
        <button type="button" className={`button ${choosePrimary ? "primary" : "secondary"}`} onClick={() => fileInput.current?.click()}>{chooseLabel}</button>
        {!isMobile && <button type="button" className={`button ${captureSupported ? "primary" : "secondary"}`} disabled={!captureSupported || capturing} onClick={startCapture}>截取游戏窗口</button>}
      </div>
      {!isMobile && <span className="dropzone-note">也可拖到这里，或在页面中粘贴</span>}
      <small>PNG / JPEG / WebP · ≤12 MB · ≤2000 万像素</small>
    </div>
    {!isMobile && !captureSupported && <p className="muted small capture-hint">当前浏览器或环境无法截取窗口，请使用“选择图片”、拖放或在页面中粘贴。</p>}
    {capturing && <div className="capture-status" role="status"><span>{captureStatus}</span>
      <button className="text-button" type="button" onClick={cancelCapture}>取消截屏</button></div>}
    {error && <p role="alert" className="error-text">{error}</p>}
    {image && <>
      <div className="image-meta"><span>{image.file.name} · {image.width}×{image.height}</span><button className="text-button" type="button" onClick={clear}>清除图片</button></div>
      <fieldset className="image-source"><legend>识别范围</legend>
        <label><input type="radio" name="image-source" checked={!useCrop} onChange={() => selectCrop(false)} /> 默认整图（自动定位）</label>
        <label><input type="radio" name="image-source" checked={useCrop} onChange={() => selectCrop(true)} /> 手动裁剪</label>
      </fieldset>
      <p className="muted">{!useCrop ? "默认上传完整原图，不在浏览器裁剪。" : cropped
        ? cropHint ?? "请保留完整棋盘和右侧所有气球库存。" : "手动裁剪为 100%，仍上传完整原图。"}</p>
      {useCrop && <fieldset className="crop-controls"><legend>裁剪范围（占原图百分比）</legend>
        {(["left", "top", "width", "height"] as const).map((field) => <label key={field}>
          {{ left: "左边距", top: "上边距", width: "宽度", height: "高度" }[field]}
          <input type="number" inputMode="numeric" min={field === "width" || field === "height" ? 1 : 0} max="100"
            value={crop[field]} onChange={(event) => changeCrop(field, Number(event.target.value))} /> %
        </label>)}
      </fieldset>}
      <div className="image-previews single"><figure><figcaption>实际上传：{uploadWidth}×{uploadHeight} 像素{cropped ? " · 裁剪输出" : " · 完整原图"}</figcaption>
        {cropped && (preparing || !preview) ? <span className="muted" role="status">正在生成裁剪图…</span> : <img src={cropped ? preview! : image.url} alt="实际将上传的图片预览" />}
      </figure></div>
    </>}
  </section>;
}
