import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";
import type { Robot, Snapshot } from "../src/types";
import fs from "node:fs";

async function waitForReady(page: Page) {
  await expect(
    page.getByRole("button", { name: "Run demo sequence" }),
  ).toBeEnabled();
}
async function submitPose(page: Page, label: string) {
  const responsePromise = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/missions") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: label, exact: true }).click();
  const response = await responsePromise;
  expect(response.status()).toBe(202);
  return (await response.json()).id as string;
}
async function missionState(page: Page, id: string) {
  const state: Snapshot = await (await page.request.get("/api/state")).json();
  return state.missions.find((mission) => mission.id === id);
}

test("both official models execute the same commands and render observed feedback", async ({
  page,
}) => {
  const errors: string[] = [];
  const badAssets: string[] = [];
  const loadedMeshes: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("response", (response) => {
    if (response.url().includes("/assets/")) {
      if (response.status() >= 400) badAssets.push(response.url());
      if (/\.(dae|stl|glb)(\?|$)/i.test(response.url()) && response.ok())
        loadedMeshes.push(response.url());
    }
  });
  const { robots }: { robots: Robot[] } = await (
    await page.request.get("/api/robots")
  ).json();
  expect(robots.length).toBeGreaterThanOrEqual(2);
  await page.goto("/");
  await expect(
    page.getByText("Live connection", { exact: true }),
  ).toBeVisible();
  fs.mkdirSync("screenshots", { recursive: true });
  const requests: Record<string, unknown>[] = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/api/missions") && request.method() === "POST")
      requests.push(request.postDataJSON());
  });
  for (const robot of robots) {
    await page
      .getByRole("group", { name: "Select robot" })
      .getByRole("button", {
        name: `${robot.manufacturer} ${robot.model}`,
        exact: true,
      })
      .click();
    await waitForReady(page);
    await expect(page.locator(".model-overlay")).toHaveCount(0, {
      timeout: 25_000,
    });
    await expect(page.locator(".tool-position")).not.toContainText("—");
    await page.locator("#duration").fill("4");
    const first = await submitPose(page, robot.poses[0].label);
    await expect
      .poll(async () => (await missionState(page, first))?.status, {
        timeout: 15_000,
      })
      .toBe("succeeded");
    await waitForReady(page);
    const before: Snapshot = await (
      await page.request.get("/api/state")
    ).json();
    const initial = before.robots.find(
      (item) => item.id === robot.id,
    )!.joint_positions;
    const second = await submitPose(page, robot.poses[1].label);
    await expect
      .poll(async () => {
        const current: Snapshot = await (
          await page.request.get("/api/state")
        ).json();
        return current.robots
          .find((item) => item.id === robot.id)!
          .joint_positions.some(
            (value, index) => Math.abs(value - initial[index]) > 0.03,
          );
      })
      .toBe(true);
    await expect
      .poll(async () => (await missionState(page, second))?.status, {
        timeout: 15_000,
      })
      .toBe("succeeded");
    await expect(page.locator(".execution-progress")).toContainText("100%");
    await expect(page.locator(".request-json")).toContainText(robot.id);
    await page.screenshot({
      path: `screenshots/${robot.id}-desktop.png`,
      fullPage: true,
    });
    const meshCount = loadedMeshes.filter((url) =>
      new URL(url).pathname.includes(
        robot.urdf_url.slice(0, robot.urdf_url.lastIndexOf("/")),
      ),
    ).length;
    expect(meshCount).toBeGreaterThan(0);
  }
  expect(requests.length).toBe(robots.length * 2);
  for (const request of requests) {
    expect(Object.keys(request).sort()).toEqual([
      "actor",
      "id",
      "inputs",
      "robot",
      "type",
    ]);
    expect(request.type).toBe("move_named");
    expect(request.inputs).toHaveProperty("pose");
    expect(request.inputs).toHaveProperty("duration", 4);
  }
  expect(errors).toEqual([]);
  expect(badAssets).toEqual([]);
});

test("switching robots preserves a running mission and software cancellation works", async ({
  page,
}) => {
  const { robots }: { robots: Robot[] } = await (
    await page.request.get("/api/robots")
  ).json();
  await page.goto("/");
  await waitForReady(page);
  await page.locator("#duration").fill("6");
  const responsePromise = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/missions") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Run demo sequence" }).click();
  const response = await responsePromise;
  expect(response.status()).toBe(202);
  const mission = await response.json();
  await expect
    .poll(async () => (await missionState(page, mission.id))?.status)
    .toBe("running");
  await page
    .getByRole("group", { name: "Select robot" })
    .getByRole("button")
    .nth(1)
    .click();
  await waitForReady(page);
  await expect
    .poll(async () => (await missionState(page, mission.id))?.status)
    .toBe("running");
  await page
    .getByRole("group", { name: "Select robot" })
    .getByRole("button")
    .nth(0)
    .click();
  await expect(page.locator(".status-pill")).toHaveText("Moving");
  await expect(
    page.getByRole("button", { name: "Run demo sequence" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Cancel motion" }).click();
  await expect
    .poll(async () => (await missionState(page, mission.id))?.status)
    .toBe("canceled");
  await waitForReady(page);
  await expect(page.locator(".execution-progress")).toContainText("Canceled");
  expect(mission.robot).toBe(robots[0].id);
});

test("mobile controls stay within the viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await waitForReady(page);
  await expect(page.locator(".model-overlay")).toHaveCount(0, {
    timeout: 25_000,
  });
  await expect(
    page.getByRole("button", { name: "Run demo sequence" }),
  ).toBeVisible();
  const dimensions = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    viewport: innerWidth,
  }));
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.viewport);
  await page
    .getByRole("button", { name: "Joint targets", exact: true })
    .click();
  await expect(
    page.getByRole("spinbutton", { name: "Joint 1 target", exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: "screenshots/mobile.png", fullPage: true });
});

test("a lost feedback channel disables motion while keeping cancellation available", async ({
  page,
}) => {
  // Only the transport failure is injected; catalog, models, and HTTP API remain real.
  await page.routeWebSocket("**/api/events", (socket) => socket.close());
  await page.goto("/");
  await expect(
    page.getByRole("group", { name: "Select robot" }).getByRole("button"),
  ).toHaveCount(2);
  await expect(
    page.getByRole("button", { name: "Run demo sequence" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Cancel motion" }),
  ).toBeEnabled();
  await expect(page.getByText("Reconnecting", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Motion controls unlock with fresh ROS feedback.", {
      exact: true,
    }),
  ).toBeVisible();
});
