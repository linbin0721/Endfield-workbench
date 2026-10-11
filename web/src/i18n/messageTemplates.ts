/**
 * Pure template matching for the centralized message bridge.
 *
 * The messages namespace stores the canonical (Simplified Chinese) runtime
 * strings of the API and the search worker, with `{{param}}` placeholders for
 * the dynamic parts. This module turns those templates into an index that can
 * recognize a raw canonical string and recover its parameters, so the display
 * layer can re-render it in the active language without changing any contract.
 *
 * It has no imports on purpose: unit tests run it directly under Node.
 */

export type MessageTemplate = {
  /** Translation key inside the messages namespace. */
  key: string;
  /** Placeholder names in template order. */
  params: string[];
  /** Number of literal characters outside placeholders. */
  literal: number;
  /** Anchored matcher for one canonical string. */
  regex: RegExp;
};

export type MessageTemplateIndex = {
  /** Templates without placeholders, matched by equality. */
  exact: Record<string, string>;
  /** Templates with placeholders, ordered from most to least specific. */
  patterns: MessageTemplate[];
};

export type TemplateMatch = {
  key: string;
  params: Record<string, string>;
};

export const PLACEHOLDER_PATTERN = /\{\{\s*([A-Za-z0-9_]+)\s*\}\}/g;

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Placeholder names of one template, in order and without duplicates. */
export function templateParams(value: string): string[] {
  const params: string[] = [];
  for (const match of String(value).matchAll(PLACEHOLDER_PATTERN)) {
    if (!params.includes(match[1])) params.push(match[1]);
  }
  return params;
}

/** Literal characters outside placeholders; used to order ambiguous matchers. */
function literalLength(value: string): number {
  return String(value).replace(PLACEHOLDER_PATTERN, "").length;
}

function compilePattern(value: string): RegExp {
  let source = "";
  let cursor = 0;
  for (const match of value.matchAll(PLACEHOLDER_PATTERN)) {
    const start = match.index ?? 0;
    source += `${escapeRegExp(value.slice(cursor, start))}([\\s\\S]+?)`;
    cursor = start + match[0].length;
  }
  source += escapeRegExp(value.slice(cursor));
  return new RegExp(`^${source}$`);
}

/**
 * Builds the matcher index from the canonical bundle. Later duplicates never
 * override an earlier key, so resource order stays authoritative.
 */
export function buildTemplateIndex(bundle: unknown): MessageTemplateIndex {
  const exact: Record<string, string> = Object.create(null) as Record<string, string>;
  const patterns: MessageTemplate[] = [];
  const walk = (prefix: string, node: unknown): void => {
    if (typeof node === "string") {
      if (!prefix) return;
      const params = templateParams(node);
      if (params.length === 0) {
        if (!(node in exact)) exact[node] = prefix;
        return;
      }
      patterns.push({ key: prefix, params, literal: literalLength(node), regex: compilePattern(node) });
      return;
    }
    if (node !== null && typeof node === "object" && !Array.isArray(node)) {
      for (const [name, child] of Object.entries(node as Record<string, unknown>)) {
        walk(prefix ? `${prefix}.${name}` : name, child);
      }
    }
  };
  walk("", bundle);
  // A more literal template is a more specific match, so it wins first.
  patterns.sort((left, right) =>
    right.literal - left.literal ||
    right.params.length - left.params.length ||
    left.key.localeCompare(right.key));
  return { exact, patterns };
}

/** Recognizes one raw canonical string; returns null when nothing matches. */
export function matchTemplate(index: MessageTemplateIndex, raw: unknown): TemplateMatch | null {
  if (raw === null || raw === undefined) return null;
  const value = String(raw);
  if (!value) return null;
  const exactKey = index.exact[value];
  if (exactKey) return { key: exactKey, params: {} };
  for (const pattern of index.patterns) {
    const match = pattern.regex.exec(value);
    if (!match) continue;
    const params: Record<string, string> = {};
    pattern.params.forEach((name, position) => { params[name] = match[position + 1]; });
    return { key: pattern.key, params };
  }
  return null;
}

// ---------------------------------------------------------------------------
// Locale-independent message rendering (display bridge core)
// ---------------------------------------------------------------------------

/**
 * A piece of UI text that is resolved while rendering, never while storing.
 * Keeping the key (and its parameters) in state means a language switch
 * re-translates errors, notices, phases and answer sources that are already on
 * screen, without re-running a request, a search or a solve.
 */
export type LocalizedText = {
  key: string;
  /** Defaults to the messages namespace. */
  ns?: string;
  /** Values may themselves be references, so composed messages stay switchable. */
  params?: Record<string, string | number | LocalizedText>;
};

/** State can hold either an authored reference or a raw canonical string. */
export type MessageText = LocalizedText | string;

export type MessageKind = "notice" | "error";

export type MessageRenderer = {
  /** Active locale, for callers that need it outside of `t`. */
  locale: string;
  /** Renders a message reference or a raw canonical runtime string. */
  render: (text: MessageText | null | undefined, kind?: MessageKind) => string;
  /** Same as `render`, named for the raw API/worker string case. */
  tm: (raw: unknown, kind?: MessageKind) => string;
};

export type MessageRendererOptions = {
  /** Locale used by the UI. */
  locale: string;
  /** Locale whose bundle holds the canonical templates (zh-CN). */
  defaultLocale: string;
  /** Canonical templates, usually the zh-CN messages bundle. */
  canonical: unknown;
  /** i18next-compatible translate; returns a string or a fallback. */
  translate: (key: string, options: Record<string, unknown>) => unknown;
  /** True when the active locale itself defines the key. */
  exists: (key: string, namespace: string) => boolean;
};

/** Recursion guard for reasons/references embedded in other messages. */
const MAX_DEPTH = 3;

/** Han characters; used to keep raw Chinese out of non-canonical locales. */
const CJK_PATTERN = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/;

export function isLocalizedText(value: unknown): value is LocalizedText {
  return Boolean(value) && typeof value === "object" && typeof (value as LocalizedText).key === "string";
}

export function msg(key: string, params?: Record<string, string | number | LocalizedText>, ns?: string): LocalizedText {
  return ns ? { key, ns, params } : { key, params };
}

/**
 * Builds the centralized display bridge.
 *
 * - Authored `{key}` references are translated with the active locale.
 * - Raw strings coming from the API, the catalog or the search worker keep
 *   their current contract; they are recognized against the canonical
 *   templates and re-rendered with their extracted parameters.
 * - The canonical locale keeps unmatched text verbatim so troubleshooting
 *   stays possible; every other language gets a localized fallback instead of
 *   raw Chinese or a translation key.
 */
export function createMessageRenderer(options: MessageRendererOptions): MessageRenderer {
  const index = buildTemplateIndex(options.canonical);
  const { locale, defaultLocale, translate: i18nTranslate, exists } = options;

  const fallback = (kind: MessageKind, depth: number): string => {
    const key = depth > 0 ? "unknown.inline" : kind === "error" ? "unknown.error" : "unknown.notice";
    const value = i18nTranslate(key, { ns: "messages" });
    return typeof value === "string" ? value : key;
  };
  const translate = (key: string, params: Record<string, unknown> | undefined,
                     ns: string, kind: MessageKind, depth: number): string => {
    if (locale !== defaultLocale && !exists(key, ns)) return fallback(kind, depth);
    const translated = i18nTranslate(key, params ? { ...params, ns } : { ns });
    return typeof translated === "string" ? translated : fallback(kind, depth);
  };
  const resolveParams = (params: Record<string, string | number | LocalizedText> | undefined,
                         kind: MessageKind, depth: number): Record<string, unknown> | undefined => {
    if (!params) return undefined;
    if (depth >= MAX_DEPTH) return { ...params };
    const resolved: Record<string, unknown> = {};
    for (const [name, value] of Object.entries(params)) {
      if (isLocalizedText(value)) { resolved[name] = render(value, kind, depth + 1); continue; }
      if (typeof value === "string" && value) {
        // A parameter is either another canonical message (translated here) or
        // plain data such as a puzzle code, a number-bearing label or a browser
        // exception. Only canonical text is re-rendered; untranslatable Chinese
        // degrades to the localized inline fallback, while data is kept as is.
        const match = matchTemplate(index, value);
        if (match) {
          resolved[name] = translate(match.key, resolveParams(match.params, kind, depth + 1), "messages", kind, depth + 1);
        } else if (locale !== defaultLocale && CJK_PATTERN.test(value)) {
          resolved[name] = fallback(kind, depth + 1);
        } else {
          resolved[name] = value;
        }
        continue;
      }
      resolved[name] = value;
    }
    return resolved;
  };
  const render = (text: MessageText | null | undefined, kind: MessageKind = "notice", depth = 0): string => {
    if (text === null || text === undefined) return "";
    if (isLocalizedText(text)) {
      return translate(text.key, resolveParams(text.params, kind, depth), text.ns ?? "messages", kind, depth);
    }
    const raw = String(text);
    if (!raw) return "";
    const match = matchTemplate(index, raw);
    if (!match) return locale === defaultLocale ? raw : fallback(kind, depth);
    return translate(match.key, resolveParams(match.params, kind, depth), "messages", kind, depth);
  };
  return {
    locale,
    render: (text, kind) => render(text, kind),
    tm: (raw, kind) => render(
      isLocalizedText(raw) || typeof raw === "string" ? raw : raw === null || raw === undefined ? "" : String(raw),
      kind,
    ),
  };
}
