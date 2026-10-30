// Save screenshots for the curator. Runs on the HOST (Alpine container has no
// glibc Chromium). I cannot read these — they exist for human review.
//
//   node web/scripts/ui-checks/shots.mjs --dir docs/ui-shots/unit-02-notes \
//     --path "/reader?id=<book>" --click "Notes"
import { mkdir } from "node:fs/promises";
import { chromium } from "playwright";

const argv = process.argv.slice(2).join(" ");
const argValue = (name) => {
  const match = argv.match(new RegExp(`--${name}\\s+([^-][^]*?)(?=\\s--|$)`));
  return match ? match[1].trim() : undefined;
};
const clicks = [...argv.matchAll(/--click\s+([^-][^]*?)(?=\s--|$)/g)].map((m) => m[1].trim());
const dir = argValue("dir") ?? "docs/ui-shots/adhoc";
const path = argValue("path") ?? "/library";

await mkdir(dir, { recursive: true });

const browser = await chromium.launch();
const sizes = [
  { width: 390, height: 844, name: "390" },
  { width: 1280, height: 900, name: "1280" },
];

for (const size of sizes) {
  for (const theme of ["dark", "light"]) {
    const context = await browser.newContext({
      viewport: { width: size.width, height: size.height },
      colorScheme: theme,
      reducedMotion: "reduce",
    });
    await context.addInitScript((mode) => {
      try {
        window.localStorage.setItem("folio-theme", mode);
      } catch {
        // ignore
      }
    }, theme);

    const page = await context.newPage();
    await page.goto("http://localhost:3000" + path, { waitUntil: "networkidle" });
    for (const label of clicks) {
      try {
        await page.getByRole("button", { name: label, exact: false }).first().click({ timeout: 4000 });
        await page.waitForTimeout(1200);
      } catch {
        console.log(`!! could not click "${label}"`);
      }
    }

    const file = `${dir}/${size.name}-${theme}.png`;
    await page.screenshot({ path: file, fullPage: false });
    console.log(`saved ${file}`);
    await context.close();
  }
}

await browser.close();
