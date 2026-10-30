// Smoke test: can Chromium launch and render our app inside this container?
// Run: docker exec folio-web-1 sh -c 'cd /workspace/web && node scripts/ui-checks/smoke.mjs'
import { chromium } from "playwright";

const url = process.argv[2] ?? "http://localhost:3000/library";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
const response = await page.goto(url, { waitUntil: "networkidle" });

const title = await page.title();
const bodyText = (await page.locator("body").innerText()).slice(0, 200);

console.log(JSON.stringify({ status: response?.status(), title, body: bodyText }, null, 2));

await browser.close();
