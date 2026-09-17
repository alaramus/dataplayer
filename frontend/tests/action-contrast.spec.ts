import { expect, test } from "@playwright/test"

import { login } from "./utils/login"

test("flat actions remain readable on the kit surface in both themes", async ({ page }) => {
  await login(page)
  await page.goto("/ui-kit")
  const toggle = page.getByTestId("theme-toggle")

  for (const theme of ["light", "dark"]) {
    if (await toggle.getAttribute("data-theme") !== theme) await toggle.click()
    await expect(toggle).toHaveAttribute("data-theme", theme)

    for (const name of ["secondary", "danger-quiet"]) {
      const button = page.getByRole("button", { name, exact: true })
      const contrast = await button.evaluate((element) => {
        const rgb = (value: string) => (value.match(/[\d.]+/g) ?? []).map(Number)
        const luminance = (channels: number[]) => {
          const linear = channels.slice(0, 3).map((channel) => {
            const value = channel / 255
            return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
          })
          return (linear[0] ?? 0) * 0.2126 + (linear[1] ?? 0) * 0.7152 + (linear[2] ?? 0) * 0.0722
        }
        let surface: Element | null = element
        let background: number[] = []
        while (surface !== null) {
          background = rgb(getComputedStyle(surface).backgroundColor)
          if (background.length === 3 || background[3] === 1) break
          surface = surface.parentElement
        }
        if (surface === null) throw new Error("No opaque surface behind action")
        const foreground = luminance(rgb(getComputedStyle(element).color))
        const ground = luminance(background)
        return (Math.max(foreground, ground) + 0.05) / (Math.min(foreground, ground) + 0.05)
      })
      expect(contrast, `${name} in ${theme}`).toBeGreaterThanOrEqual(4.5)
    }
  }
})
