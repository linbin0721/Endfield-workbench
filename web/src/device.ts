// Device classification for the shared image import UI.
// Only user agent, platform and touch capability decide the mode: viewport width
// and a lone touch signal must not move a desktop into the mobile layout.
type UserAgentDataLike = { mobile?: boolean };

export function isMobileLikeDevice(): boolean {
  if (typeof navigator === "undefined") return false;
  const agent = navigator.userAgent || "";
  const mobileHint = (navigator as Navigator & { userAgentData?: UserAgentDataLike }).userAgentData?.mobile;
  if (mobileHint === true) return true;
  if (/Android|iPhone|iPad|iPod/i.test(agent)) return true;
  // iPadOS 13+ Safari and iPad browsers report a desktop "Macintosh" user agent.
  // A Mac platform with multi-touch stays mobile while a touch-enabled Windows
  // machine keeps its "Win32" platform and remains a desktop.
  const platform = navigator.platform || "";
  const macPlatform = /Mac/i.test(platform) || /Macintosh/i.test(agent);
  return macPlatform && navigator.maxTouchPoints > 1;
}
