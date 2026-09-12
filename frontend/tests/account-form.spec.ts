import { expect, test } from "@playwright/test"

import { login } from "./utils/login"
import { openAdmin } from "./utils/people"

test("account fields identify a new password and keep empty labels above the input", async ({ page }) => {
  await login(page)
  await openAdmin(page)
  await page.getByTestId("new-user").click()

  for (const field of ["user-email", "user-name", "user-password"]) {
    const input = page.getByTestId(field)
    await expect(input).toHaveValue("")
    await expect(input).toHaveAttribute("autocomplete", field === "user-password" ? "new-password" : "off")
    const label = page.getByRole("dialog").locator("label").filter({ has: input })
    await expect(label).toHaveClass(/q-field--float/)
  }

  await page.getByTestId("user-cancel").click()
  await expect(page.getByRole("dialog")).toHaveCount(0)
})
