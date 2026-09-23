import type { Page } from "@playwright/test"

/** Keep unrelated account attention out of scenarios that assert a job count. */
export async function isolateJobAttention(page: Page) {
  await page.route("**/api/v1/shares/requests**", (route) => route.fulfill({
    json: { data: [], count: 0 },
  }))
  await page.route("**/api/v1/ai/conversations**", (route) => route.fulfill({
    json: { data: [], count: 0 },
  }))
  await page.route("**/api/v1/metrics/restarts**", (route) => route.fulfill({
    json: { hosts: [], window_seconds: 3600 },
  }))
}
