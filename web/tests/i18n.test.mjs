/**
 * Translation audit for the four interface languages (EW-025/B).
 *
 * Scope: resources only. It never runs the app or the worker; it verifies
 *
 *   1. the zh-CN bundles are structurally sound (non-empty values, valid
 *      placeholders, no ambiguous canonical templates),
 *   2. every other locale keeps the same keys and interpolation parameters as
 *      zh-CN (missing, extra or incomplete translations fail the audit),
 *   3. every translation key referenced by the UI exists in its namespace,
 *   4. the centralized message bridge recognizes the canonical strings that the
 *      API, the catalog and the search worker can actually return.
 *
 * Usage: node --test tests/i18n.test.mjs
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { buildTemplateIndex, templateParams, matchTemplate, createMessageRenderer, msg } from "../src/i18n/messageTemplates.ts";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const srcDir = path.join(projectRoot, "src");
const localeRoot = path.join(srcDir, "i18n", "locales");
const repositoryRoot = path.resolve(projectRoot, "..");
const LOCALES = ["zh-CN", "en", "ja", "ko"];
const TRANSLATED_NAMESPACES = ["common", "messages", "balloon", "circuit", "calculator"];
const STRICT = true;

const readJson = (file) => JSON.parse(fs.readFileSync(file, "utf8"));

function flatten(node, prefix = "", out = {}) {
  if (node !== null && typeof node === "object" && !Array.isArray(node)) {
    for (const [key, value] of Object.entries(node)) flatten(value, prefix ? `${prefix}.${key}` : key, out);
  } else {
    out[prefix] = node;
  }
  return out;
}

function bundle(locale, namespace) {
  const file = path.join(localeRoot, locale, `${namespace}.json`);
  return fs.existsSync(file) ? flatten(readJson(file)) : null;
}

const zhBundles = Object.fromEntries(
  TRANSLATED_NAMESPACES.map((namespace) => [namespace, bundle("zh-CN", namespace)]));

function resolveKey(namespace, key) {
  const flat = zhBundles[namespace];
  return flat && Object.hasOwn(flat, key) ? flat[key] : undefined;
}

/** Any namespace that defines the full key, used for cross-namespace literals. */
function keyExists(key) {
  return TRANSLATED_NAMESPACES.some((namespace) => resolveKey(namespace, key) !== undefined);
}

function walkFiles(directory, collected = []) {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) walkFiles(full, collected);
    else collected.push(full);
  }
  return collected;
}

// ---------------------------------------------------------------------------
// 1. zh-CN structural integrity
// ---------------------------------------------------------------------------

test("zh-CN bundles are complete and use valid placeholders", () => {
  for (const namespace of TRANSLATED_NAMESPACES) {
    const flat = zhBundles[namespace];
    assert.ok(flat, `missing zh-CN/${namespace}.json`);
    for (const [key, value] of Object.entries(flat)) {
      assert.equal(typeof value, "string", `${namespace}:${key} must be a string`);
      assert.notEqual(value.trim(), "", `${namespace}:${key} must not be empty`);
      const open = (value.match(/\{\{/g) ?? []).length;
      const close = (value.match(/\}\}/g) ?? []).length;
      assert.equal(open, close, `${namespace}:${key} has unbalanced {{ }} placeholders`);
      const names = templateParams(value);
      assert.equal(new Set(names).size, names.length, `${namespace}:${key} repeats a placeholder name`);
    }
  }
});

test("canonical message templates match themselves without ambiguity", () => {
  const index = buildTemplateIndex(readJson(path.join(localeRoot, "zh-CN", "messages.json")));
  const messages = readJson(path.join(localeRoot, "zh-CN", "messages.json"));
  const flat = flatten(messages);
  for (const [key, value] of Object.entries(flat)) {
    const match = matchTemplate(index, value);
    assert.ok(match, `messages:${key} does not match any template`);
    assert.equal(match.key, key, `messages:${key} is shadowed by ${match.key}`);
  }
  // Two different templates must not both claim the same canonical string.
  for (const [key, value] of Object.entries(flat)) {
    const hits = index.patterns.filter((pattern) => pattern.regex.test(value)).map((pattern) => pattern.key);
    assert.deepEqual(hits, hits.includes(key) ? [key] : hits,
      `messages:${key} is ambiguous: ${hits.join(", ")}`);
    assert.ok(hits.length <= 1, `messages:${key} matches several templates: ${hits.join(", ")}`);
  }
});

// ---------------------------------------------------------------------------
// 2. Translation parity (EN/JA/KO vs zh-CN)
// ---------------------------------------------------------------------------

test("other locales mirror the zh-CN keys and interpolation parameters", () => {
  const pending = [];
  const problems = [];
  for (const locale of LOCALES.filter((item) => item !== "zh-CN")) {
    for (const namespace of TRANSLATED_NAMESPACES) {
      const translated = bundle(locale, namespace);
      if (!translated) {
        pending.push(`${locale}/${namespace}: file missing`);
        continue;
      }
      const source = zhBundles[namespace];
      assert.deepEqual(Object.keys(translated).sort(), Object.keys(source).sort(), `${locale}/${namespace}: translation keys differ`);
      for (const [key, value] of Object.entries(source)) {
        if (!Object.hasOwn(translated, key)) {
          pending.push(`${locale}/${namespace}:${key}`);
          continue;
        }
        const target = translated[key];
        const expected = templateParams(value).sort();
        const actual = templateParams(target).sort();
        if (expected.join(",") !== actual.join(",")) {
          problems.push(`${locale}/${namespace}:${key} placeholders ${actual.join(",") || "-"} != ${expected.join(",") || "-"}`);
        }
        if (typeof target === "string" && target.trim() === "") {
          problems.push(`${locale}/${namespace}:${key} is empty`);
        }
        // Latin/Korean translations must not silently keep Chinese source text.
        if (locale !== "ja" && /[\u4e00-\u9fff]/.test(target ?? "")) {
          problems.push(`${locale}/${namespace}:${key} still contains Chinese: ${JSON.stringify(target)}`);
        }
      }
    }
  }
  assert.deepEqual(problems, [], problems.join("\n"));
  if (pending.length > 0) {
    console.log(`i18n audit: ${pending.length} translation entr${pending.length === 1 ? "y" : "ies"} pending (EN/JA/KO).`);
  }
  if (STRICT) {
    assert.deepEqual(pending, [], `translations pending:\n${pending.slice(0, 20).join("\n")}`);
  }
});

// ---------------------------------------------------------------------------
// 3. UI keys used by the source exist in the zh-CN resources
// ---------------------------------------------------------------------------

/** Keys built at runtime from a stable family; the audit expands them explicitly. */
const DYNAMIC_KEY_FAMILIES = [
  ["common", ["task.queued", "task.running", "task.succeeded", "task.failed", "task.cancelled"]],
  ["calculator", ["attributes.strength", "attributes.agility", "attributes.intellect", "attributes.will"]],
  ["balloon", ["problems.liftMissing", "problems.countMissing", "problems.liftInvalid", "problems.countInvalid",
    "problems.liftDuplicate", "problems.noUsable", "problems.noInventory", "problems.tooManyKinds"]],
  ["circuit", ["problems.targetMissing", "problems.targetInvalid", "problems.cellUnknown", "problems.fixedChannel"]],
  ["circuit", ["reasons.row_targets", "reasons.column_targets", "reasons.rejected", "reasons.unsatisfiable",
    "reasons.solver_limit", "reasons.validation_failed"]],
  ["calculator", ["bench.short.strength", "bench.short.agility", "bench.short.intellect", "bench.short.will"]],

  // Referenced inside i18n/messages.ts, which the source scan skips.
  ["messages", ["unknown.notice", "unknown.error", "unknown.inline"]],
];

test("every translation key used by the UI exists in zh-CN", () => {
  const files = walkFiles(srcDir).filter((file) =>
    /\.(ts|tsx)$/.test(file) &&
    !file.includes(`${path.sep}i18n${path.sep}`) &&
    !file.includes(`${path.sep}generated${path.sep}`));
  const missing = [];
  // A key literal is a dotted string whose first segment is a resource group.
  const literalPattern = /["'`]([a-zA-Z][A-Za-z0-9]*(?:\.[A-Za-z0-9_]+)+)["'`]/g;
  // Calls with a literal key, so the bound namespace can be checked exactly.
  const callPattern = /\b(t|tc|tm|msg|render)\(\s*"([A-Za-z][\w.]*)"/g;
  const groups = new Set(TRANSLATED_NAMESPACES.flatMap((namespace) =>
    Object.keys(zhBundles[namespace]).map((key) => key.split(".")[0])));
  const isFileLike = (key) => /\.(ts|tsx|json|png|css|mjs|js|html|svg|webp|jpg)$/.test(key);
  for (const file of files) {
    const relative = path.relative(projectRoot, file);
    const text = fs.readFileSync(file, "utf8");
    for (const match of text.matchAll(literalPattern)) {
      const key = match[1];
      if (isFileLike(key)) continue;
      if (!groups.has(key.split(".")[0])) continue;
      if (!keyExists(key)) missing.push(`${relative}: ${key}`);
    }
    // The bound namespace must resolve the key on its own; a page namespace does
    // not fall back to `common`, so `t("service.retry")` in a page bound to
    // `balloon` would render the raw key.
    const declared = [...text.matchAll(/useAppTranslation\(\s*"([a-z-]+)"\s*\)/g)].map((item) => item[1]);
    if (!declared.length) continue;
    for (const match of text.matchAll(callPattern)) {
      const [full, fn, key] = match;
      if (isFileLike(key) || !groups.has(key.split(".")[0])) continue;
      const tail = text.slice((match.index ?? 0) + full.length, (match.index ?? 0) + full.length + 200);
      let namespace = tail.match(/ns:\s*"([a-z-]+)"/)?.[1] ?? null;
      if (!namespace && (fn === "msg" || fn === "render" || fn === "tm")) {
        namespace = tail.match(/,\s*"(common|messages|balloon|circuit|calculator)"\s*\)/)?.[1] ?? null;
      }
      if (!namespace && fn === "tc") namespace = "common";
      if (!namespace && fn === "t") namespace = declared[0];
      if (!namespace) continue;
      if (resolveKey(namespace, key) === undefined) {
        missing.push(`${relative}: ${key} is not in the "${namespace}" namespace used here`);
      }
    }
  }
  assert.deepEqual([...new Set(missing)], [], `translation keys missing from zh-CN:\n${[...new Set(missing)].join("\n")}`);
  for (const [namespace, keys] of DYNAMIC_KEY_FAMILIES) {
    for (const key of keys) {
      assert.notEqual(resolveKey(namespace, key), undefined, `${namespace}:${key} is missing (dynamic key family)`);
    }
  }
});

// ---------------------------------------------------------------------------
// 4. The message bridge recognizes the canonical runtime strings
// ---------------------------------------------------------------------------

/**
 * Canonical strings that are intentionally not bridged, each with its reason.
 * Everything else the backend or the unmodified solver modules can show must
 * match a `messages` template.
 */
const BRIDGE_IGNORES = new Set([
  // OCR text markers and regex fragments; never displayed.
  "N级回收气球", "升力", "升力 N",
  // FastAPI application title.
  "终末地解谜 API",
  // Capability metadata (tool names/descriptions) that the UI does not render.
  "浮空回收", "源石电路",
  "以棋盘几何中心为支点，升力按行列距离加权，左右与上下分别平衡；每格至多一个气球，使用全部库存",
  "按通道满足每行和每列的覆盖数；障碍格不可覆盖，固定格计入约束；全部库存拼块均可旋转且必须使用",
  // Prefix of a composed derive message whose complete template exists.
  "第 {row} 行库存的升力和数量均缺失：",
  // circuitDisplay.ts color names are normalized at the display boundary
  // (features/circuit/colors.ts), not through the canonical message templates.
  "红色", "橙色", "黄色", "绿色", "青色", "蓝色", "紫色", "品红色", "未知颜色",
]);

/** Turn a Python f-string fragment into the runtime shape of the message. */
const normalizePlaceholders = (value) => value.includes("{{") ? value : value.replace(/\{(\w+)\}/g, "{{$1}}");

function canonicalCorpus() {
  const apiFiles = walkFiles(path.join(repositoryRoot, "api", "app")).filter((file) => file.endsWith(".py"));
  const frontendFiles = ["puzzle.ts", "circuit.ts", "api.ts", "calculator/search.ts", "calculator/search.worker.ts"]
    .map((name) => path.join(srcDir, ...name.split("/")));
  const corpus = new Map();
  for (const file of [...apiFiles, ...frontendFiles]) {
    const text = fs.readFileSync(file, "utf8");
    for (const match of text.matchAll(/"((?:[^"\\\n]|\\.)*[\u4e00-\u9fff](?:[^"\\\n]|\\.)*)"/g)) {
      const value = match[1];
      if (value.length < 3 || value.length > 160) continue;
      if (/[\\\[\]()^$|*+?]/.test(value)) continue; // regex fragments, not messages
      if (BRIDGE_IGNORES.has(value)) continue;
      corpus.set(value, path.relative(projectRoot, file));
    }
  }
  return corpus;
}

test("message bridge recognizes the canonical API/worker strings", () => {
  const index = buildTemplateIndex(readJson(path.join(localeRoot, "zh-CN", "messages.json")));
  const unmatched = [];
  for (const [value, file] of canonicalCorpus()) {
    const normalized = normalizePlaceholders(value);
    if (!matchTemplate(index, normalized)) unmatched.push(`${file}: ${value}`);
  }
  assert.deepEqual(unmatched, [], `canonical strings without a messages template:\n${unmatched.join("\n")}`);
});

// ---------------------------------------------------------------------------
// 5. The display bridge re-translates stored messages per locale
// ---------------------------------------------------------------------------

/** Minimal i18next stand-in: lookup + {{param}} interpolation, zh-CN fallback. */
function fakeI18n(locale, bundles) {
  const lookup = (lng, namespace, key) => {
    const flat = bundles[lng]?.[namespace];
    return flat && Object.hasOwn(flat, key) ? flat[key] : undefined;
  };
  const interpolate = (value, params) => String(value).replace(/\{\{\s*(\w+)\s*\}\}/g,
    (_, name) => (params && name in params ? String(params[name]) : ""));
  return {
    translate: (key, options = {}) => {
      const namespace = options.ns ?? "messages";
      const value = lookup(locale, namespace, key) ?? lookup("zh-CN", namespace, key);
      return value === undefined ? key : interpolate(value, options);
    },
    exists: (key, namespace) => lookup(locale, namespace, key) !== undefined,
  };
}

// Synthetic target-language bundle for the renderer test only; product EN/JA/KO
// resources are owned by the translation batch and must never live here.
const SYNTHETIC = {
  messages: {
    "unknown.notice": "UNKNOWN-NOTICE",
    "unknown.error": "UNKNOWN-ERROR",
    "unknown.inline": "INLINE",
    "balloon.stockMissing": "No balloon stock was recognized; fill in lift and count manually.",
    "balloon.derivedLift": "Row {{row}}: derived lift {{lift}} × {{count}} (target {{target}}).",
    "catalog.verificationFailed": "Not saved to {{code}}: {{reason}}.",
    "catalog.reasonNoSolution": "no solution was found",
  },
  balloon: {
    "answer.sourceCode": "Puzzle {{code}}",
  },
};

const REAL_BUNDLES = {
  "zh-CN": Object.fromEntries(TRANSLATED_NAMESPACES.map((namespace) =>
    [namespace, flatten(readJson(path.join(localeRoot, "zh-CN", `${namespace}.json`)))])),
};

test("message renderer translates canonical strings with their parameters", () => {
  const canonical = REAL_BUNDLES["zh-CN"].messages;
  const zh = createMessageRenderer({
    locale: "zh-CN", defaultLocale: "zh-CN", canonical, ...fakeI18n("zh-CN", REAL_BUNDLES),
  });
  const raw = "图片中未识别到库存，请手动填写。";
  assert.equal(zh.render(raw), raw, "zh-CN keeps the canonical text");
  const derived = "第 2 行库存缺少升力：已按目标总升力 18 唯一推导为升力 3 × 2 个，请核对。";
  assert.equal(zh.render(derived), derived, "zh-CN keeps parameters in place");
  assert.equal(zh.render("完全未知的中文提示"), "完全未知的中文提示", "zh-CN keeps unmatched text for troubleshooting");

  const en = createMessageRenderer({
    locale: "en", defaultLocale: "zh-CN", canonical, ...fakeI18n("en", { ...REAL_BUNDLES, en: SYNTHETIC }),
  });
  assert.equal(en.render(raw), SYNTHETIC.messages["balloon.stockMissing"]);
  assert.equal(en.render(derived), "Row 2: derived lift 3 × 2 (target 18).");
  assert.equal(en.render("完全未知的中文提示"), "UNKNOWN-NOTICE");
  assert.equal(en.render("完全未知的中文提示", "error"), "UNKNOWN-ERROR");
  assert.equal(en.render(""), "");
  assert.equal(en.render(null), "");
  assert.equal(en.render("toString"), "UNKNOWN-NOTICE", "object prototype names are ordinary unknown messages");
  assert.equal(en.render("__proto__", "error"), "UNKNOWN-ERROR");
});

test("message renderer re-translates stored references and nested messages", () => {
  const canonical = REAL_BUNDLES["zh-CN"].messages;
  const zh = createMessageRenderer({
    locale: "zh-CN", defaultLocale: "zh-CN", canonical, ...fakeI18n("zh-CN", REAL_BUNDLES),
  });
  const source = msg("answer.sourceCode", { code: "WL-A1001" }, "balloon");
  assert.equal(zh.render(source), "题号 WL-A1001");
  assert.equal(zh.render(msg("answer.sourceScreenshot", undefined, "balloon")), "截图识别");

  const nested = msg("catalog.verificationFailed", {
    reason: "没有可行解", code: "WL-A1001",
  });
  assert.equal(zh.render(nested), "本次识别题面没有可行解，未写入题号 WL-A1001 的目录；请换一张清晰截图或使用已有候选。");

  const en = createMessageRenderer({
    locale: "en", defaultLocale: "zh-CN", canonical, ...fakeI18n("en", { ...REAL_BUNDLES, en: SYNTHETIC }),
  });
  assert.equal(en.render(source), "Puzzle WL-A1001");
  assert.equal(en.render(nested), "Not saved to WL-A1001: no solution was found.");
  // A nested reason without a translation degrades to the localized inline
  // fallback instead of leaking raw Chinese.
  assert.equal(en.render(msg("catalog.verificationFailed", { reason: "复核后没有可行解", code: "WL-A1001" })),
    "Not saved to WL-A1001: INLINE.");
  // A reference without a translation in the active locale uses the fallback too.
  assert.equal(en.render(msg("answer.sourceScreenshot", undefined, "balloon")), "UNKNOWN-NOTICE");
});
