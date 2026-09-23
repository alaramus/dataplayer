import { expect, test } from "@playwright/test"

import { login } from "./utils/login"

test("application and Quasar controls draw Symbols Outlined in both themes", async ({ page }) => {
  await login(page)
  await page.goto("/ui-kit")
  const toggle = page.getByTestId("theme-toggle")

  for (const theme of ["light", "dark"]) {
    if (await toggle.getAttribute("data-theme") !== theme) await toggle.click()
    await expect(toggle).toHaveAttribute("data-theme", theme)
    await expect(page.getByRole("button", { name: "User menu" }).locator(".q-icon")).toHaveClass(/material-symbols-outlined/)
    await expect(page.getByRole("button", { name: "Add", exact: true }).locator(".q-icon")).toHaveClass(/material-symbols-outlined/)
    await expect(page.locator(".material-icons")).toHaveCount(0)
    await page.screenshot({ path: `test-results/symbols-interface-${theme}.png` })
  }
})
