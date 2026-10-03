// One-shot desktop window capture for the shared image input.
// The stream is requested directly inside the click task, the first drawable
// frame becomes a PNG File, and every track is stopped as soon as possible.

export const maxCaptureBytes = 12 * 1024 * 1024;
export const maxCapturePixels = 20_000_000;
const frameWaitMs = 10_000;
const encodeWaitMs = 15_000;

export type ScreenCaptureFailure =
  | "unsupported"
  | "pending"
  | "denied"
  | "unavailable"
  | "no-frame"
  | "ended"
  | "too-many-pixels"
  | "too-large"
  | "encode-failed"
  | "aborted"
  | "failed";

export class ScreenCaptureError extends Error {
  constructor(public readonly code: ScreenCaptureFailure, message: string) {
    super(message);
    this.name = "ScreenCaptureError";
  }
}

export function isScreenCaptureSupported(): boolean {
  if (typeof window === "undefined" || typeof navigator === "undefined") return false;
  if (!window.isSecureContext) return false;
  return typeof navigator.mediaDevices?.getDisplayMedia === "function";
}

// `displaySurface: "window"` and `selfBrowserSurface: "exclude"` are hints only;
// the browser still decides which sources it offers and never force-selects one.
type DisplayMediaHints = DisplayMediaStreamOptions & {
  preferCurrentTab?: boolean;
  selfBrowserSurface?: "include" | "exclude";
};

function stopTracks(stream: MediaStream) {
  for (const track of stream.getTracks()) {
    try { track.stop(); } catch { /* the track has already ended */ }
  }
}

function requestFailure(error: unknown): ScreenCaptureError {
  const name = error instanceof Error ? error.name : "";
  if (name === "NotAllowedError") return new ScreenCaptureError("denied", "Display capture was not granted");
  if (name === "InvalidStateError") return new ScreenCaptureError("pending", "Display capture cannot start in the current state");
  if (name === "AbortError") return new ScreenCaptureError("aborted", "Display capture was aborted");
  if (name === "SecurityError") return new ScreenCaptureError("unsupported", "Display capture is blocked in this context");
  if (name === "NotFoundError" || name === "NotReadableError" || name === "OverconstrainedError" || name === "TrackStartError") {
    return new ScreenCaptureError("unavailable", "The selected window could not be read");
  }
  return new ScreenCaptureError("failed", "Display capture failed");
}

// Settles on the first of: result, timeout or abort. An abort rejects at once and
// removes both the timer and the listener, so the caller can clean up immediately;
// a late result afterwards only resolves an already-settled promise and is ignored.
function withTimeout<T>(promise: Promise<T>, timeoutMs: number, timeout: () => ScreenCaptureError, signal?: AbortSignal): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    let settled = false;
    const finish = (settle: () => void) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
      settle();
    };
    const onAbort = () => finish(() => reject(new ScreenCaptureError("aborted", "Display capture was aborted")));
    const timer = window.setTimeout(() => finish(() => reject(timeout())), timeoutMs);
    if (signal?.aborted) { onAbort(); return; }
    signal?.addEventListener("abort", onAbort);
    promise.then(
      (value) => finish(() => resolve(value)),
      (error) => finish(() => reject(error)),
    );
  });
}

function screenshotFilename(date = new Date()): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  const stamp = `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}-${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`;
  return `screenshot-${stamp}.png`;
}

function isDrawable(video: HTMLVideoElement): boolean {
  return video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA && video.videoWidth > 0 && video.videoHeight > 0;
}

function waitForDrawableFrame(video: HTMLVideoElement, track: MediaStreamTrack, signal?: AbortSignal): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    let settled = false;
    let timer = 0;
    let interval = 0;
    let frameCallback: number | null = null;

    const cleanup = () => {
      window.clearTimeout(timer);
      window.clearInterval(interval);
      video.removeEventListener("loadeddata", check);
      video.removeEventListener("canplay", check);
      video.removeEventListener("playing", check);
      video.removeEventListener("error", onVideoError);
      track.removeEventListener("ended", onTrackEnded);
      signal?.removeEventListener("abort", onAbort);
      if (frameCallback !== null && typeof video.cancelVideoFrameCallback === "function") {
        video.cancelVideoFrameCallback(frameCallback);
      }
    };
    const finish = (error?: ScreenCaptureError) => {
      if (settled) return;
      settled = true;
      cleanup();
      if (error) reject(error); else resolve();
    };
    function check() {
      if (settled) return;
      if (track.readyState === "ended") { finish(new ScreenCaptureError("ended", "The shared window was closed")); return; }
      if (isDrawable(video)) finish();
    }
    function onVideoError() { finish(new ScreenCaptureError("no-frame", "The video element reported an error")); }
    function onTrackEnded() { finish(new ScreenCaptureError("ended", "The shared window was closed")); }
    function onAbort() { finish(new ScreenCaptureError("aborted", "Display capture was aborted")); }

    timer = window.setTimeout(() => finish(new ScreenCaptureError("no-frame", "No video frame arrived in time")), frameWaitMs);
    interval = window.setInterval(check, 50);
    video.addEventListener("loadeddata", check);
    video.addEventListener("canplay", check);
    video.addEventListener("playing", check);
    video.addEventListener("error", onVideoError);
    track.addEventListener("ended", onTrackEnded);
    signal?.addEventListener("abort", onAbort);
    if (typeof video.requestVideoFrameCallback === "function") {
      frameCallback = video.requestVideoFrameCallback(() => { frameCallback = null; check(); });
    }
    check();
  });
}

async function captureFrame(stream: MediaStream, signal?: AbortSignal): Promise<File> {
  const track = stream.getVideoTracks()[0];
  if (!track) throw new ScreenCaptureError("no-frame", "The capture stream has no video track");

  // The video element stays outside the visible page but is rendered offscreen so
  // browsers deliver and compose frames; it is removed again in the cleanup below.
  const host = document.createElement("div");
  host.setAttribute("aria-hidden", "true");
  host.style.cssText = "position:fixed;left:-10000px;top:0;width:1px;height:1px;overflow:hidden;pointer-events:none;";
  const video = document.createElement("video");
  video.muted = true;
  video.playsInline = true;
  video.autoplay = true;
  host.appendChild(video);
  document.body.appendChild(host);

  try {
    video.srcObject = stream;
    void video.play().catch(() => { /* a live stream can still deliver frames without playback */ });
    await waitForDrawableFrame(video, track, signal);

    const width = video.videoWidth;
    const height = video.videoHeight;
    if (!width || !height) throw new ScreenCaptureError("no-frame", "No drawable video frame");
    if (width * height > maxCapturePixels) throw new ScreenCaptureError("too-many-pixels", "Capture exceeds the pixel limit");

    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    if (!context) throw new ScreenCaptureError("encode-failed", "Canvas is unavailable");
    context.drawImage(video, 0, 0, width, height);
    stopTracks(stream);

    const blob = await withTimeout(
      new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png")),
      encodeWaitMs,
      () => new ScreenCaptureError("encode-failed", "PNG encoding timed out"),
      signal,
    );
    if (!blob) throw new ScreenCaptureError("encode-failed", "PNG encoding failed");
    if (blob.size > maxCaptureBytes) throw new ScreenCaptureError("too-large", "Capture exceeds the size limit");
    return new File([blob], screenshotFilename(), { type: "image/png" });
  } finally {
    video.pause();
    video.srcObject = null;
    host.remove();
  }
}

export async function captureGameWindow(signal?: AbortSignal, onStreamReady?: () => void): Promise<File> {
  if (!isScreenCaptureSupported()) throw new ScreenCaptureError("unsupported", "Window capture is unavailable");
  if (signal?.aborted) throw new ScreenCaptureError("aborted", "Display capture was aborted");

  // getDisplayMedia is invoked synchronously in the click task: nothing is awaited
  // before the call, and the source picker cannot be dismissed programmatically.
  let stream: MediaStream;
  try {
    const options: DisplayMediaHints = {
      audio: false,
      video: { displaySurface: "window" },
      preferCurrentTab: false,
      selfBrowserSurface: "exclude",
    };
    stream = await navigator.mediaDevices.getDisplayMedia(options);
  } catch (error) {
    if (signal?.aborted) throw new ScreenCaptureError("aborted", "Display capture was aborted");
    throw requestFailure(error);
  }

  try {
    if (signal?.aborted) throw new ScreenCaptureError("aborted", "Display capture was aborted");
    onStreamReady?.();
    return await captureFrame(stream, signal);
  } finally {
    // A late resolve after unmount, clear, image change or cancellation still
    // releases the captured source immediately.
    stopTracks(stream);
  }
}
