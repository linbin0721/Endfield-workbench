import styles from "./BootError.module.css";

type BootMessages = { error: string; retry: string };

/**
 * Shown when the first language bundle cannot load, before React mounts.
 * Plain DOM, styled by the design tokens already applied to <html>.
 */
export function renderBootError(container: HTMLElement, messages: BootMessages): void {
  const notice = document.createElement("section");
  notice.className = styles.notice;
  notice.setAttribute("role", "alert");
  const text = document.createElement("p");
  text.className = styles.text;
  text.textContent = messages.error;
  const retry = document.createElement("button");
  retry.type = "button";
  retry.className = styles.retry;
  retry.textContent = messages.retry;
  retry.onclick = () => window.location.reload();
  notice.append(text, retry);
  container.replaceChildren(notice);
}
