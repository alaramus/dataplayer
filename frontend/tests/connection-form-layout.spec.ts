import { expect, test } from "@playwright/test"

import { pickAdapterType } from "./utils/connectors"
import { login } from "./utils/login"

for (const theme of ["light", "dark"] as const) {
  test(`connection form keeps aligned labels and reflows in ${theme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme })
    await login(page)
    await pickAdapterType(page, "postgres")
    const frame = page.getByRole("dialog", { name: "New connection", exact: true })
    const host = page.getByTestId("field-host")
    const database = page.getByTestId("field-database")
    const label = frame.getByText("Host", { exact: true })
    const hostBox = await host.boundingBox()
    const databaseBox = await database.boundingBox()
    const labelBox = await label.boundingBox()
    if (!hostBox || !databaseBox || !labelBox) throw new Error("Missing form field")
    expect(hostBox.x).toBeCloseTo(databaseBox.x, 0)
    expect(labelBox.x + labelBox.width).toBeLessThan(hostBox.x)
    expect(hostBox.height).toBeLessThanOrEqual(36)
    await expect(frame.getByRole("combobox", { name: "Authentication", exact: true })).toBeVisible()
    await frame.screenshot({ path: `test-results/connection-form-${theme}.png` })

    await host.focus()
    const focusColor = await host.evaluate((element) => {
      const control = element.closest(".q-field")?.querySelector(".q-field__control")
      if (!control) throw new Error("Missing field control")
      return getComputedStyle(control, "::after").borderColor
    })
    const channels = (focusColor.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number)
    expect(channels).toHaveLength(3)
    expect(Math.max(...channels) - Math.min(...channels)).toBe(0)
    await page.getByTestId("connector-name").fill("")
    await page.getByTestId("apply-connector").click()
    await expect(page.getByTestId("connector-name")).toHaveAttribute("aria-invalid", "true")
    const errorColor = await page.getByTestId("connector-name").evaluate((element) => {
      const control = element.closest(".q-field")?.querySelector(".q-field__control")
      if (!control) throw new Error("Missing field control")
      return getComputedStyle(control, "::after").borderColor
    })
    expect(errorColor).not.toBe(focusColor)
    await page.getByTestId("connector-name").fill("PostgreSQL")
    await page.getByTestId("connector-name").blur()

    await page.setViewportSize({ width: 390, height: 700 })
    await expect.poll(async () => {
      const currentLabel = await label.boundingBox()
      const currentInput = await host.boundingBox()
      return currentLabel && currentInput ? currentInput.y - currentLabel.y - currentLabel.height : -1
    }).toBeGreaterThanOrEqual(0)
    await expect.poll(() => frame.locator(".app-form").evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
    const url = await page.getByTestId("connector-url").boundingBox()
    const copy = await page.getByTestId("copy-url").boundingBox()
    if (!url || !copy) throw new Error("Missing URL controls")
    expect(copy.x).toBeGreaterThan(url.x)
    expect(Math.abs(copy.y + copy.height / 2 - url.y - url.height / 2)).toBeLessThan(3)
    await expect(page.getByTestId("cancel-connector")).toBeInViewport()
    await frame.screenshot({ path: `test-results/connection-form-${theme}-narrow.png` })
  })
}
