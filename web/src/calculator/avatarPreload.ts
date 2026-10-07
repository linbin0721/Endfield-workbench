import { getEntityMedia } from "./media.ts";

const IMAGE_TIMEOUT_MS = 15_000;
const BACKGROUND_CONCURRENCY = 2;

/** Warm only character portraits while the calculator is mounted; return its teardown. */
export function preloadCharacterAvatars(characterIds: readonly string[], defaultCharacterId?: string): () => void {
  const connection = (navigator as Navigator & {
    connection?: { saveData?: boolean; effectiveType?: string };
  }).connection;
  if (connection?.saveData || connection?.effectiveType === "2g" || connection?.effectiveType === "slow-2g") {
    return () => {};
  }

  const defaultUrl = defaultCharacterId ? getEntityMedia("characters", defaultCharacterId)?.imageUrl : undefined;
  const urls = new Set(characterIds.flatMap((id) => {
    const url = getEntityMedia("characters", id)?.imageUrl;
    return url ? [url] : [];
  }));
  if (defaultUrl) urls.delete(defaultUrl);
  const queue = [...urls];
  const inFlight = new Set<() => void>();
  let stopped = false;
  let defaultPending = Boolean(defaultUrl);
  let defaultActive = false;
  let idleId: number | undefined;
  let idleTimer: number | undefined;

  const cancelIdle = () => {
    if (idleId !== undefined) window.cancelIdleCallback(idleId);
    if (idleTimer !== undefined) window.clearTimeout(idleTimer);
    idleId = undefined;
    idleTimer = undefined;
  };

  const schedule = () => {
    if (stopped || document.hidden || idleId !== undefined || idleTimer !== undefined) return;
    if (defaultPending || defaultActive || queue.length === 0 || inFlight.size >= BACKGROUND_CONCURRENCY) return;
    const run = () => {
      idleId = undefined;
      idleTimer = undefined;
      if (stopped || document.hidden) return;
      while (queue.length > 0 && inFlight.size < BACKGROUND_CONCURRENCY) {
        const url = queue.shift();
        if (url) startImage(url, "low", schedule);
      }
    };
    if (typeof window.requestIdleCallback === "function") {
      idleId = window.requestIdleCallback(run, { timeout: 1000 });
    } else {
      idleTimer = window.setTimeout(run, 100);
    }
  };

  const startImage = (url: string, priority: "high" | "low", done: () => void) => {
    const image = new Image();
    let settled = false;
    let decoding = false;
    let timer: number | undefined;
    const settle = (cancelDownload = false) => {
      if (settled) return;
      settled = true;
      if (timer !== undefined) window.clearTimeout(timer);
      image.onload = null;
      image.onerror = null;
      inFlight.delete(cancel);
      if (cancelDownload) image.removeAttribute("src");
      if (!stopped) done();
    };
    const cancel = () => settle(true);
    const loaded = () => {
      if (stopped || settled || decoding) return;
      decoding = true;
      if (typeof image.decode !== "function") { settle(); return; }
      try {
        void image.decode().then(() => settle(), () => settle(true));
      } catch {
        settle(true);
      }
    };
    image.fetchPriority = priority;
    image.decoding = "async";
    image.onload = loaded;
    image.onerror = cancel;
    inFlight.add(cancel);
    // One deadline covers both transfer and decode, including a decoder that never settles.
    timer = window.setTimeout(cancel, IMAGE_TIMEOUT_MS);
    image.src = url;
    if (image.complete) {
      if (image.naturalWidth > 0) loaded();
      else cancel();
    }
  };

  const resume = () => {
    if (stopped || document.hidden) { cancelIdle(); return; }
    if (defaultPending && defaultUrl) {
      defaultPending = false;
      defaultActive = true;
      startImage(defaultUrl, "high", () => {
        defaultActive = false;
        schedule();
      });
    } else {
      schedule();
    }
  };
  document.addEventListener("visibilitychange", resume);
  resume();
  return () => {
    stopped = true;
    cancelIdle();
    document.removeEventListener("visibilitychange", resume);
    for (const cancel of inFlight) cancel();
    queue.length = 0;
  };
}
