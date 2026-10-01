/** Record the real local ROS demo; this script never synthesizes robot feedback. */
import { chromium } from "@playwright/test";
import fs from "node:fs";
const origin = process.env.IAC_BASE_URL || "http://127.0.0.1:8000";
const delay = (milliseconds) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));
const { robots } = await (await fetch(`${origin}/api/robots`)).json();
async function completed(id) {
  for (let attempt = 0; attempt < 60; attempt++) {
    const state = await (await fetch(`${origin}/api/state`)).json();
    const mission = state.missions.find((item) => item.id === id);
    if (mission?.status === "succeeded") return;
    if (["failed", "canceled"].includes(mission?.status))
      throw new Error(`Setup mission ${mission.status}: ${mission.detail}`);
    await delay(500);
  }
  throw new Error("Timed out waiting for a controller result");
}
// Set a known initial pose using the same live API before recording begins.
for (const robot of robots) {
  const response = await fetch(`${origin}/api/missions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      id: `record-${crypto.randomUUID().slice(0, 8)}`,
      type: "move_named",
      robot: robot.id,
      actor: "demo-recording",
      inputs: { pose: robot.poses[0].id, duration: 4 },
    }),
  });
  if (!response.ok) throw new Error(await response.text());
  await completed((await response.json()).id);
}
fs.mkdirSync("screenshots", { recursive: true });
const browser = await chromium.launch({
  args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 1100 },
  recordVideo: {
    dir: "test-results/recording",
    size: { width: 1440, height: 1100 },
  },
});
const page = await context.newPage();
const video = page.video();
await page.goto(origin);
await page.locator(".model-overlay").waitFor({ state: "hidden" });
await page.getByRole("button", { name: "Run demo sequence" }).waitFor();
await delay(1500);
for (let index = 0; index < Math.min(2, robots.length); index++) {
  await page
    .getByRole("group", { name: "Select robot" })
    .getByRole("button")
    .nth(index)
    .click();
  await page.locator(".model-overlay").waitFor({ state: "hidden" });
  await delay(700);
  await page
    .getByRole("button", { name: robots[index].poses[1].label, exact: true })
    .click();
  await delay(6200);
}
await page.getByRole("button", { name: "Run demo sequence" }).click();
await delay(6200); // Continue into the second segment so the cancel visibly interrupts motion.
await page.getByRole("button", { name: "Cancel motion" }).click();
await delay(1800);
await page.locator(".details-grid").scrollIntoViewIfNeeded();
await delay(1800);
await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
await delay(1300);
await context.close();
await video.saveAs("screenshots/demo.webm");
await video.delete();
await browser.close();
console.log("Recorded screenshots/demo.webm from the live ROS platform.");
