import { useCallback, useEffect, useRef, useState } from "react";

type Crop = { left: number; top: number; width: number; height: number };
type ImageInfo = { file: File; width: number; height: number; url: string };
export type ImageSelection = { blob: Blob; filename: string };
const initialCrop: Crop = { left: 0, top: 0, width: 100, height: 100 };
const allowed = new Set(["image/png", "image/jpeg", "image/webp"]);
const maxBytes = 12 * 1024 * 1024;
const maxPixels = 20_000_000;
const isFullCrop = (crop: Crop) => crop.left === 0 && crop.top === 0 && crop.width === 100 && crop.height === 100;

export default function ImageInput({ onChanged }: { onChanged: (selection: ImageSelection | null, changed?: boolean) => void }) {
  const [image, setImage] = useState<ImageInfo | null>(null);
  const [crop, setCrop] = useState<Crop>(initialCrop);
  const [useCrop, setUseCrop] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const originalUrl = useRef<string | null>(null);
  const cropUrl = useRef<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const selection = useRef(0);
  const previewVersion = useRef(0);

  const release = useCallback(() => {
    if (originalUrl.current) URL.revokeObjectURL(originalUrl.current);
    if (cropUrl.current) URL.revokeObjectURL(cropUrl.current);
    originalUrl.current = null;
    cropUrl.current = null;
  }, []);

  useEffect(() => () => { selection.current++; release(); }, [release]);

  const clear = useCallback(() => {
    selection.current++; previewVersion.current++;
    release();
    setImage(null); setPreview(null); setPreparing(false); setCrop(initialCrop); setUseCrop(false); setError("");
    if (fileInput.current) fileInput.current.value = "";
    onChanged(null);
  }, [onChanged, release]);

  const choose = useCallback(async (file?: File) => {
    if (!file) return;
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
  }, [onChanged, release]);

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

  return <section className="panel" aria-labelledby="image-title">
    <div className="section-heading"><div><span className="eyebrow">01 / 图片</span><h2 id="image-title">导入画面</h2></div><span className="badge">选图仅本地预览</span></div>
    <p className="muted">选择、拖放或粘贴截图；手机可从相册选图。只有点击“识别并求解”后才会上传选定范围。</p>
    <div className={`dropzone ${dragging ? "dragging" : ""}`} onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); void choose(event.dataTransfer.files[0]); }}>
      <input ref={fileInput} type="file" accept="image/png,image/jpeg,image/webp" id="image-file"
        onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; void choose(file); }} />
      <label htmlFor="image-file" className="button primary">{image ? "更换图片" : "选择图片"}</label>
      <span>也可拖到这里，或在页面中粘贴</span>
      <small>PNG / JPEG / WebP · ≤12 MB · ≤2000 万像素</small>
    </div>
    {error && <p role="alert" className="error-text">{error}</p>}
    {image && <>
      <div className="image-meta"><span>{image.file.name} · {image.width}×{image.height}</span><button className="text-button" type="button" onClick={clear}>清除图片</button></div>
      <fieldset className="image-source"><legend>识别范围</legend>
        <label><input type="radio" name="image-source" checked={!useCrop} onChange={() => selectCrop(false)} /> 默认整图（自动定位）</label>
        <label><input type="radio" name="image-source" checked={useCrop} onChange={() => selectCrop(true)} /> 手动裁剪</label>
      </fieldset>
      <p className="muted">{!useCrop ? "默认上传完整原图，不在浏览器裁剪。" : cropped ? "请保留完整棋盘和右侧所有气球库存。" : "手动裁剪为 100%，仍上传完整原图。"}</p>
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
