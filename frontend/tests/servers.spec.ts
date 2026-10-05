import { expect, test } from "@playwright/test"
import type { BrowserContext, Page } from "@playwright/test"

const alpha = "https://alpha.dataplayer.test/player"
const beta = "https://beta.dataplayer.test"
const profiles = [{ name: "Alpha", url: alpha }, { name: "Beta", url: beta }]
interface SentRequest { url: string; authorization: string | undefined }

async function fakeServers(context: BrowserContext, requests: SentRequest[]) {
  await context.route(/^https:\/\/(alpha|beta)\.dataplayer\.test\//, async (route) => {
    const request = route.request()
    requests.push({ url: request.url(), authorization: request.headers().authorization })
    const url = new URL(request.url())
    const headers = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*", "Access-Control-Allow-Methods": "*" }
    if (request.method() === "OPTIONS") { await route.fulfill({ status: 204, headers }); return }
    let body: unknown = []
    if (url.pathname.endsWith("/utils/server-info")) body = { product: "dataplayer", client_api_version: 1 }
    else if (url.pathname.endsWith("/login/access-token")) body = { access_token: "beta-token", token_type: "bearer" }
    else if (url.pathname.endsWith("/users/me")) body = { id: "00000000-0000-0000-0000-000000000001", email: "test@example.com", is_active: true, is_superuser: false, full_name: "Test user" }
    else if (/\/connectors\/?$/.test(url.pathname)) body = { data: [], count: 0 }
    else if (/\/jobs\/?$/.test(url.pathname)) body = { data: [], count: 0, active_count: 0 }
    await route.fulfill({ status: 200, contentType: "application/json", headers, body: JSON.stringify(body) })
  })
}

async function choose(page: Page, name: string) {
  await page.getByTestId("server-switcher").click()
  await page.getByTestId("server-profile").filter({ hasText: name }).getByRole("button", { name: "Connect", exact: true }).click()
}

/** The footer shows the server as one icon; hovering it names the address. */
async function expectServer(page: Page, url: string) {
  await page.getByTestId("server-switcher").hover()
  await expect(page.locator(".app-tooltip")).toContainText(url)
}

test("switching isolates authentication and leaves another browser tab on its server", async ({ page, context }) => {
  const requests: SentRequest[] = []
  await fakeServers(context, requests)
  await context.addInitScript(({ profiles, alpha }) => {
    if (localStorage.getItem("server-test-seeded")) return
    localStorage.setItem("server-test-seeded", "true")
    localStorage.setItem("dataplayer:servers:v1", JSON.stringify(profiles))
    localStorage.setItem("dataplayer:legacy-server:v1", alpha)
    localStorage.setItem("access_token", "alpha-token")
    // With the tour open, switching servers would stop at its closing
    // question instead of reaching the login page under test.
    localStorage.setItem("dataplayer-onboarding-done", "1")
  }, { profiles, alpha })
  await page.goto("/?server=" + encodeURIComponent(alpha))
  await expectServer(page, alpha)
  const other = await context.newPage()
  await other.goto("/?server=" + encodeURIComponent(alpha))
  await expect(other.getByTestId("user-menu")).toBeVisible()

  await choose(page, "Beta")
  await expect(page.getByTestId("login-email")).toBeVisible()
  await expect(page.getByTestId("server-switcher")).toContainText("Beta")
  await expectServer(other, alpha)
  await expect(other.getByTestId("user-menu")).toBeVisible()

  await page.getByTestId("login-email").fill("test@example.com")
  await page.getByTestId("login-password").fill("beta-password")
  await page.getByTestId("login-submit").click()
  await expect(page.getByTestId("user-menu")).toBeVisible()
  await page.reload()
  await expectServer(page, beta)
  await expect(page.getByTestId("user-menu")).toBeVisible()
  expect(requests.some((request) => request.url === alpha + "/api/v1/users/me" && request.authorization === "Bearer alpha-token")).toBe(true)
  expect(requests.some((request) => request.url === beta + "/api/v1/users/me" && request.authorization === "Bearer beta-token")).toBe(true)
  expect(requests.filter((request) => request.url.startsWith(beta)).some((request) => request.authorization === "Bearer alpha-token")).toBe(false)
  expect(requests.filter((request) => request.url.endsWith("/utils/server-info")).every((request) => !request.authorization)).toBe(true)

  await page.getByTestId("user-menu").click()
  await page.getByText("Sign out", { exact: true }).click()
  await expect(page.getByTestId("login-email")).toBeVisible()
  await expect(other.getByTestId("user-menu")).toBeVisible()
  await choose(page, "Alpha")
  await expect(page.getByTestId("user-menu")).toBeVisible()
  await other.close()
})

test("an unfamiliar shared link waits for consent and rejects an incompatible server", async ({ page }) => {
  const requests: SentRequest[] = []
  const target = "https://unknown.dataplayer.test"
  await page.route(target + "/**", async (route) => {
    requests.push({ url: route.request().url(), authorization: route.request().headers().authorization })
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ product: "dataplayer", client_api_version: 99 }), headers: { "Access-Control-Allow-Origin": "*" } })
  })
  await page.goto("/s/example-share?server=" + encodeURIComponent(target))
  await expect(page.getByTestId("link-server-url")).toHaveValue(target)
  expect(requests).toHaveLength(0)
  await page.getByTestId("link-server-connect").click()
  await expect(page.getByText("This server is not compatible with this version of DataPlayer.")).toBeVisible()
  expect(requests).toHaveLength(1)
  expect(requests[0]?.authorization).toBeUndefined()
  expect(await page.evaluate(() => localStorage.getItem("dataplayer:servers:v1"))).toBeNull()
})

test("server management stays available when the configured backend is down", async ({ page, context }) => {
  await page.route("**/api/v1/utils/server-info", (route) => route.abort())
  await page.goto("/login")
  await expect(page.getByTestId("login-submit")).toBeDisabled()
  await page.getByTestId("server-switcher").click()
  await page.getByTestId("server-add").click()
  await page.getByTestId("server-name").fill("Alpha")
  await page.getByTestId("server-url").fill(alpha)
  await page.getByTestId("server-save").click()
  await expect(page.getByTestId("server-profile").filter({ hasText: "Alpha" })).toBeVisible()
  await page.getByTestId("server-profile").filter({ hasText: "Alpha" }).getByRole("button", { name: "Edit server", exact: true }).click()
  await page.getByTestId("server-name").fill("My Alpha")
  await page.getByTestId("server-save").click()
  await page.getByTestId("server-profile").filter({ hasText: "My Alpha" }).getByRole("button", { name: "Remove server", exact: true }).click()
  await expect(page.getByTestId("server-profile").filter({ hasText: "My Alpha" })).toHaveCount(0)

  // Saving an address does not require the offline default to respond.
  await page.getByTestId("server-add").click()
  await page.getByTestId("server-name").fill("Alpha")
  await page.getByTestId("server-url").fill(alpha)
  await page.getByTestId("server-save").click()
  await page.unroute("**/api/v1/utils/server-info")
  await fakeServers(context, [])
  await page.getByTestId("server-profile").filter({ hasText: "Alpha" }).getByRole("button", { name: "Connect", exact: true }).click()
  await expect(page.getByTestId("server-switcher")).toContainText("Alpha")
  await expect(page.getByTestId("login-submit")).toBeEnabled()
})

test("the server panel closes with Escape or a click outside", async ({ page }) => {
  await page.goto("/login")
  await page.getByTestId("server-switcher").click()
  await expect(page.getByTestId("server-manager")).toBeVisible()
  await page.keyboard.press("Escape")
  await expect(page.getByTestId("server-manager")).toHaveCount(0)
  await page.getByTestId("server-switcher").click()
  await page.mouse.click(500, 100)
  await expect(page.getByTestId("server-manager")).toHaveCount(0)
})
