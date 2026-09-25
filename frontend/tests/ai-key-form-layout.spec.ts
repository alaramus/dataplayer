import { expect, test } from "@playwright/test"

import { expectFieldActionAligned } from "./utils/layout"
import { login } from "./utils/login"

for (const theme of ["light", "dark"] as const) {
  test(`AI key form keeps its label, reveal action and footer in ${theme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme })
    await login(page)
    // Every provider reads as keyed, so the window shows its fullest footer
    // without a key being stored.
    await page.route("**/api/v1/ai/settings", async (route) => {
      if (route.request().method() !== "GET") return route.fallback()
      const response = await route.fetch()
      const json = await response.json() as { keys: { provider: string; set: boolean }[] }
      await route.fulfill({ response, json: { ...json, keys: json.keys.map((key) => ({ ...key, set: true })) } })
    })
    await page.getByTestId("space-ai").click()
    await page.getByTestId("ai-open-settings").click()
    await page.getByTestId("ai-model").click()
    await page.getByRole("option", { name: /Claude Opus 5 API key/, exact: false })
      .getByRole("button", { name: "Manage Anthropic API key" }).click()
    const content = page.getByTestId("ai-key-dialog")
    const frame = page.getByRole("dialog").filter({ has: content })
    // The provider is named once, by the title, rather than on a line of its own.
    const subtitle = await content.locator(".window-dialog__subtitle").textContent()
    const provider = /every (.+) model/.exec(subtitle ?? "")?.[1]
    expect(provider, "the subtitle names the provider").toBeTruthy()
    await expect(frame).toHaveAccessibleName(`${provider ?? ""} API key`)
    await expect(content.getByText(provider ?? "", { exact: true })).toHaveCount(0)

    const key = page.getByTestId("ai-provider-key")
    await expect(key).toHaveAccessibleName("API key")
    await expect(key).toHaveAttribute("type", "password")
    await expect(key).toHaveAttribute("autocomplete", "new-password")
    await expect(key).toHaveAttribute("placeholder", "A key is already set")
    const label = await frame.getByText("API key", { exact: true }).boundingBox()
    const field = await key.boundingBox()
    if (!label || !field) throw new Error("Missing key field or label")
    expect(label.x + label.width).toBeLessThan(field.x)
    expect(field.height).toBeLessThanOrEqual(36)

    const reveal = frame.getByRole("button", { name: "Show key", exact: true })
    await expectFieldActionAligned(key, reveal)
    const before = await frame.boundingBox()
    await reveal.click()
    await expect(key).toHaveAttribute("type", "text")
    await expect(frame.getByRole("button", { name: "Hide key", exact: true })).toBeVisible()
    expect(await frame.boundingBox()).toEqual(before)

    await expect(page.getByTestId("ai-key-save")).toBeDisabled()
    await key.fill("example-key")
    await expect(page.getByTestId("ai-key-save")).toBeEnabled()
    for (const name of ["Clear", "Check", "Close", "Save"]) {
      await expect(frame.getByRole("button", { name, exact: true })).toBeVisible()
    }
    const body = content.locator(".window-dialog__content")
    expect(await body.evaluate((el) => el.scrollHeight <= el.clientHeight)).toBe(true)
    await frame.screenshot({ path: `test-results/ai-key-form-${theme}.png` })

    await page.setViewportSize({ width: 390, height: 600 })
    await expect.poll(async () => {
      const narrowLabel = await frame.getByText("API key", { exact: true }).boundingBox()
      const narrowField = await key.boundingBox()
      return narrowLabel && narrowField ? narrowField.y - narrowLabel.y - narrowLabel.height : -1
    }).toBeGreaterThanOrEqual(0)
    await expectFieldActionAligned(key, frame.getByRole("button", { name: "Hide key", exact: true }))
    await expect.poll(() => content.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
    await expect(page.getByTestId("ai-key-save")).toBeInViewport()
    await frame.screenshot({ path: `test-results/ai-key-form-${theme}-narrow.png` })
    await frame.getByRole("button", { name: "Close", exact: true }).click()
    await expect(content).toHaveCount(0)
  })
}
