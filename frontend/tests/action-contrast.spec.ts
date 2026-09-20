import { expect, test } from "@playwright/test"

import { login } from "./utils/login"

test("actions remain readable with neutral emphasis in both themes", async ({ page }) => {
  await login(page)
  await page.goto("/ui-kit")
  const toggle = page.getByTestId("theme-toggle")

  for (const theme of ["light", "dark"]) {
    if (await toggle.getAttribute("data-theme") !== theme) await toggle.click()
    await expect(toggle).toHaveAttribute("data-theme", theme)

    for (const name of ["primary", "secondary", "danger", "danger-quiet"]) {
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

    for (const name of ["primary", "secondary"]) {
      const channels = await page.getByRole("button", { name, exact: true }).evaluate((element, variant) => {
        const style = getComputedStyle(element)
        return ((variant === "primary" ? style.backgroundColor : style.color).match(/[\d.]+/g) ?? []).slice(0, 3).map(Number)
      }, name)
      expect(channels).toHaveLength(3)
      expect(Math.max(...channels) - Math.min(...channels)).toBe(0)
    }
    await page.getByRole("button", { name: "primary", exact: true }).focus()
    await expect(page.getByRole("button", { name: "primary", exact: true })).toBeFocused()
    await page.screenshot({ path: `test-results/ui-kit-neutral-${theme}.png` })
  }
})

/**
 * U12: Escape did nothing while the frame had focus, which is where focus goes
 * when a question opens, and Cancel left the keyboard on the page body rather
 * than on the command that had asked.
 */
test("a question is dismissed with Escape and hands the keyboard back", async ({ page }) => {
  await login(page)
  await page.goto("/ui-kit")
  const ask = page.getByRole("button", { name: "Confirm", exact: true })

  await ask.click()
  await expect(page.getByTestId("confirm-message")).toBeVisible()
  await page.keyboard.press("Escape")
  await expect(page.getByTestId("confirm-message")).toHaveCount(0)
  await expect(ask).toBeFocused()

  // And the same by the way out that was already there.
  await ask.click()
  await page.getByTestId("confirm-cancel").click()
  await expect(page.getByTestId("confirm-message")).toHaveCount(0)
  await expect(ask).toBeFocused()
})
