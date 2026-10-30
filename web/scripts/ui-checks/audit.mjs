// Text-only UI audit for one screen: structure, layout facts, contrast,
// touch targets, token drift, and axe violations.
//
// Runs on the HOST, not in the web container: the container is Alpine/musl and
// Playwright only ships glibc Chromium builds.
//
// Usage:
//   node web/scripts/ui-checks/audit.mjs \
//     --path "/reader?id=<book>" --width 390 --theme dark \
//     --click "Notes" --click "Databases" [--compact]
//
// Prints a text report. No screenshots, no pixel comparison.
import { chromium } from "playwright";
import { AxeBuilder } from "@axe-core/playwright";

const argv = process.argv.slice(2).join(" ");
const argValue = (name) => {
  const match = argv.match(new RegExp(`--${name}\\s+([^-][^]*?)(?=\\s--|$)`));
  return match ? match[1].trim() : undefined;
};
const clicks = [...argv.matchAll(/--click\s+([^-][^]*?)(?=\s--|$)/g)].map((m) => m[1].trim());
const compact = /--compact(\s|$)/.test(argv);

const base = "http://localhost:3000";
const path = argValue("path") ?? "/library";
const width = Number(argValue("width") ?? 390);
const height = width >= 1000 ? 900 : 844;
const theme = argValue("theme") ?? "dark";
const label = argValue("label") ?? `${path} ${width}`;

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width, height },
  colorScheme: theme,
  reducedMotion: "reduce",
});

// The app themes from localStorage via an inline script in layout.tsx, not from
// prefers-color-scheme — setting colorScheme alone left every "dark" run light.
await context.addInitScript((mode) => {
  try {
    window.localStorage.setItem("folio-theme", mode);
  } catch {
    // storage unavailable; the report shows light-mode numbers
  }
}, theme);

const page = await context.newPage();
const consoleErrors = [];
page.on("pageerror", (error) => consoleErrors.push(String(error)));
page.on("console", (message) => {
  if (message.type() === "error") consoleErrors.push(message.text());
});

await page.goto(base + path, { waitUntil: "networkidle" });

for (const clickLabel of clicks) {
  try {
    await page.getByRole("button", { name: clickLabel, exact: false }).first().click({ timeout: 4000 });
    await page.waitForTimeout(900);
  } catch {
    console.log(`!! could not click "${clickLabel}"`);
  }
}

const report = await page.evaluate(() => {
  const parseColor = (value) => {
    const match = value.match(/rgba?\(([^)]+)\)/);
    if (!match) return null;
    const parts = match[1].split(",").map((n) => parseFloat(n.trim()));
    return { r: parts[0], g: parts[1], b: parts[2], a: parts[3] ?? 1 };
  };

  const luminance = ({ r, g, b }) => {
    const channel = (c) => {
      const s = c / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
  };

  const contrast = (fg, bg) => {
    const l1 = luminance(fg);
    const l2 = luminance(bg);
    const [light, dark] = l1 > l2 ? [l1, l2] : [l2, l1];
    return (light + 0.05) / (dark + 0.05);
  };

  const over = (top, bottom) => ({
    r: top.r * top.a + bottom.r * (1 - top.a),
    g: top.g * top.a + bottom.g * (1 - top.a),
    b: top.b * top.a + bottom.b * (1 - top.a),
    a: 1,
  });

  // Composite every layer up the tree: bg-accent/10 is a wash over what is
  // behind it, not the accent colour itself.
  const effectiveBackground = (element) => {
    const layers = [];
    let node = element;
    while (node) {
      const bg = parseColor(getComputedStyle(node).backgroundColor);
      if (bg && bg.a > 0.01) layers.push(bg);
      if (bg && bg.a >= 0.99) break;
      node = node.parentElement;
    }
    let result = { r: 255, g: 255, b: 255, a: 1 };
    for (const layer of layers.reverse()) result = over(layer, result);
    return result;
  };

  const visible = (element) => {
    const rect = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    return (
      rect.width > 0 &&
      rect.height > 0 &&
      style.visibility !== "hidden" &&
      style.display !== "none" &&
      Number(style.opacity) > 0.05
    );
  };

  const describe = (element) => {
    const tag = element.tagName.toLowerCase();
    const text = (element.textContent ?? "").trim().replace(/\s+/g, " ").slice(0, 44);
    const aria = element.getAttribute("aria-label");
    return `<${tag}${aria ? ` aria-label="${aria}"` : ""}> ${text}`;
  };

  const all = [...document.querySelectorAll("body *")].filter(visible);

  // A clipped ellipsis and an sr-only 1px box both report scrollWidth larger
  // than clientWidth by design; neither is a layout overflow.
  const overflow = all
    .filter((element) => {
      const style = getComputedStyle(element);
      if (style.textOverflow === "ellipsis") return false;
      if (element.clientWidth <= 1 || element.clientHeight <= 1) return false;
      return element.scrollWidth - element.clientWidth > 1;
    })
    .slice(0, 8)
    .map((element) => `${describe(element)} ${element.scrollWidth}>${element.clientWidth}`);

  const interactive = all.filter((element) =>
    element.matches("button, a[href], input, select, textarea, [role=button], [role=tab]"),
  );
  const smallTargets = interactive
    .map((element) => {
      const rect = element.getBoundingClientRect();
      return { element, w: Math.round(rect.width), h: Math.round(rect.height) };
    })
    .filter(({ w, h }) => w < 44 || h < 44)
    .map(({ element, w, h }) => `${w}x${h} ${describe(element).slice(0, 40)}`);

  const unnamed = interactive
    .filter((element) => {
      const name =
        (element.getAttribute("aria-label") ?? "") ||
        (element.textContent ?? "").trim() ||
        (element.getAttribute("title") ?? "");
      return name.length === 0;
    })
    .map(describe);

  const collect = (fn) => [...new Set(all.map(fn).filter(Boolean))];
  const hasText = (element) => (element.textContent ?? "").trim().length > 0;
  const fontSizes = collect((element) =>
    hasText(element) ? getComputedStyle(element).fontSize : null,
  ).sort();
  const fontWeights = collect((element) =>
    hasText(element) ? getComputedStyle(element).fontWeight : null,
  ).sort();
  const radii = collect((element) => {
    const radius = getComputedStyle(element).borderRadius;
    return radius && radius !== "0px" ? radius : null;
  }).sort();
  const textColors = collect((element) =>
    hasText(element) ? getComputedStyle(element).color : null,
  ).sort();

  const contrastRows = [];
  for (const element of all) {
    const ownText = [...element.childNodes]
      .filter((node) => node.nodeType === Node.TEXT_NODE)
      .map((node) => node.textContent.trim())
      .join(" ")
      .trim();
    if (!ownText) continue;
    const style = getComputedStyle(element);
    const fg = parseColor(style.color);
    if (!fg) continue;
    const ratio = contrast(fg, effectiveBackground(element));
    const sizePx = parseFloat(style.fontSize);
    const isLarge = sizePx >= 24 || (sizePx >= 18.66 && Number(style.fontWeight) >= 700);
    contrastRows.push({
      ratio: Math.round(ratio * 100) / 100,
      required: isLarge ? 3 : 4.5,
      size: style.fontSize,
      weight: style.fontWeight,
      text: ownText.replace(/\s+/g, " ").slice(0, 36),
    });
  }
  contrastRows.sort((a, b) => a.ratio - b.ratio);

  const distinctFailingTexts = [
    ...new Map(contrastRows.filter((r) => r.ratio < r.required).map((r) => [r.text, r])).values(),
  ].slice(0, 8);

  const headings = [...document.querySelectorAll("h1, h2, h3, h4")]
    .filter(visible)
    .slice(0, 6)
    .map((element) => {
      const style = getComputedStyle(element);
      return `${(element.textContent ?? "").trim().slice(0, 26)} → ${style.fontSize}/${style.fontWeight}`;
    });

  return {
    darkApplied: document.documentElement.classList.contains("dark"),
    failingCount: contrastRows.filter((r) => r.ratio < r.required).length,
    worst: contrastRows[0] ?? null,
    distinctFailingTexts,
    overflow,
    smallTargets,
    unnamed,
    fontSizes,
    fontWeights,
    radii,
    textColors,
    headings,
    buttonCount: interactive.length,
    textChars: document.body.innerText.length,
  };
});

let axeSummary = [];
try {
  const axe = await new AxeBuilder({ page }).analyze();
  axeSummary = axe.violations.map((v) => `${v.impact}:${v.id}(${v.nodes.length})`);
} catch (error) {
  axeSummary = [`axe failed: ${error}`];
}

const aria = compact ? "" : await page.locator("body").ariaSnapshot();

console.log("=".repeat(78));
console.log(`SCREEN ${label} | ${width}px | theme=${theme} dark=${report.darkApplied} | ${report.buttonCount} controls, ${report.textChars} chars`);
console.log("=".repeat(78));

if (!compact) {
  console.log(`\n-- aria snapshot (truncated) --\n${aria.split("\n").slice(0, 55).join("\n")}`);
}

console.log(`\ncontrast: ${report.failingCount} failing; worst ${report.worst?.ratio}:1 "${report.worst?.text}" (${report.worst?.size}/${report.worst?.weight})`);
for (const row of report.distinctFailingTexts) {
  console.log(`   ${row.ratio}:1 (<${row.required}) ${row.size}/${row.weight} "${row.text}"`);
}
console.log(`\ntargets<44px: ${report.smallTargets.length}`);
for (const line of report.smallTargets.slice(0, 8)) console.log(`   ${line}`);
console.log(`overflow: ${report.overflow.length}`);
for (const line of report.overflow.slice(0, 6)) console.log(`   ${line}`);
console.log(`unnamed controls: ${report.unnamed.length}`);
for (const line of report.unnamed.slice(0, 5)) console.log(`   ${line}`);
console.log(`sizes ${report.fontSizes.join("/")} | weights ${report.fontWeights.join("/")} | radii ${report.radii.join("/")}`);
console.log(`text colors ${report.textColors.join(" ")}`);
console.log(`headings: ${report.headings.join(" | ")}`);
console.log(`axe: ${axeSummary.join(" ") || "none"}`);
if (consoleErrors.length) console.log(`console errors: ${consoleErrors.length} — ${consoleErrors[0].slice(0, 120)}`);

await browser.close();
