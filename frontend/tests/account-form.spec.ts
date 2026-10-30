import { expect, test } from "@playwright/test"

import { login } from "./utils/login"
import { openAdmin } from "./utils/people"

for (const theme of ["light", "dark"] as const) {
  test(`account forms keep labels and validation, and leave the password to its owner, in ${theme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme })
    await login(page)
    const user = { id: "layout-user", email: "layout@example.test", full_name: "Example person", is_active: true, is_superuser: false }
    await page.route("**/api/v1/users/?*", (route) => route.fulfill({ json: { data: [user], count: 1 } }))
    let update: unknown
    await page.route("**/api/v1/users/layout-user", async (route) => {
      update = route.request().postDataJSON()
      await route.fulfill({ json: user })
    })
    await openAdmin(page)
    await page.getByTestId("new-user").click()
    const frame = page.getByRole("dialog", { name: "New user", exact: true })
    const before = await frame.boundingBox()
    // Nobody types a password for somebody else: the owner chooses it through
    // the link handed out after saving.
    await expect(page.getByTestId("user-password")).toHaveCount(0)
    for (const [field, name] of [["user-email", "Email"], ["user-name", "Name"]] as const) {
      const input = page.getByTestId(field)
      await expect(input).toHaveValue("")
      await expect(input).toHaveAccessibleName(name)
      await expect(input).toHaveAttribute("autocomplete", "off")
      const labelBox = await frame.getByText(name, { exact: true }).boundingBox()
      const inputBox = await input.boundingBox()
      if (!labelBox || !inputBox) throw new Error("Missing field or label")
      expect(labelBox.x + labelBox.width).toBeLessThan(inputBox.x)
      expect(inputBox.height).toBeLessThanOrEqual(36)
    }
    await page.getByTestId("user-save").click()
    await expect(page.getByTestId("user-email")).toHaveAttribute("aria-invalid", "true")
    expect(await frame.boundingBox()).toEqual(before)
    await frame.screenshot({ path: `test-results/account-form-${theme}.png` })
    await page.setViewportSize({ width: 390, height: 500 })
    await expect.poll(async () => {
      const label = await frame.getByText("Email", { exact: true }).boundingBox()
      const field = await page.getByTestId("user-email").boundingBox()
      return label && field ? field.y - label.y - label.height : -1
    }).toBeGreaterThanOrEqual(0)
    const body = page.getByTestId("user-dialog").locator(".window-dialog__content")
    await expect.poll(() => body.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
    await expect(page.getByTestId("user-save")).toBeInViewport()
    await frame.screenshot({ path: `test-results/account-form-${theme}-narrow.png` })
    await body.evaluate((el) => { el.scrollTop = el.scrollHeight })
    await expect(page.getByTestId("user-superuser")).toBeInViewport()
    await page.getByTestId("user-cancel").click()

    await page.setViewportSize({ width: 1280, height: 720 })
    await page.getByTestId("edit-user-layout@example.test").click()
    const edit = page.getByRole("dialog", { name: "Edit user — layout@example.test", exact: true })
    const editBody = page.getByTestId("user-dialog").locator(".window-dialog__content")
    await expect.poll(() => editBody.evaluate((el) => el.scrollHeight <= el.clientHeight)).toBe(true)
    await expect(page.getByTestId("user-password")).toHaveCount(0)
    await page.getByTestId("user-name").fill("Updated person")
    await page.getByTestId("user-active").uncheck()
    await page.getByTestId("user-superuser").check()
    await edit.screenshot({ path: `test-results/account-edit-${theme}.png` })
    await page.getByTestId("user-save").click()
    await expect(edit).toHaveCount(0)
    expect(update).toEqual({ email: user.email, full_name: "Updated person", is_active: false, is_superuser: true })
  })
}
