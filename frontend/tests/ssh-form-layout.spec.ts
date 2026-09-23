import { expect, test } from "@playwright/test"

import { login } from "./utils/login"

for (const theme of ["light", "dark"] as const) {
  test(`SSH forms keep compact fields and reachable actions in ${theme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme })
    await login(page)
    await page.route("**/api/v1/ssh-keys/", (route) => route.fulfill({ json: [
      {
        id: "layout-key", name: "Layout key", algorithm: "ssh-ed25519",
        public_key: "ssh-ed25519 example", fingerprint: "SHA256:example",
        passphrase_mode: "ask", unlocked_until: null, created_at: null, used_by: [],
      },
      {
        id: "layout-key-two", name: "Second key", algorithm: "ssh-ed25519",
        public_key: "ssh-ed25519 example-two", fingerprint: "SHA256:example-two",
        passphrase_mode: "none", unlocked_until: null, created_at: null, used_by: [],
      },
    ] }))
    await page.route("**/api/v1/ssh-keys/generate", (route) => route.fulfill({
      status: 400, json: { detail: "The key could not be generated" },
    }))
    await page.goto("/preferences")
    const footer = page.getByTestId("app-footer")
    const footerHeight = (await footer.boundingBox())!.height
    const firstKey = page.getByTestId("ssh-key-Layout key")
    const secondKey = page.getByTestId("ssh-key-Second key")
    await expect(firstKey).toHaveCSS("background-color", "rgba(0, 0, 0, 0)")
    await expect(firstKey).toHaveCSS("border-radius", "0px")
    await expect(secondKey).toHaveCSS("border-top-width", "1px")
    await expect(secondKey).toHaveCSS("border-top-style", "solid")
    await page.setViewportSize({ width: 390, height: 600 })
    await expect.poll(() => page.getByTestId("ssh-keys").evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
    await expect(page.getByTestId("ssh-key-copy-Layout key")).toBeVisible()
    await expect(page.getByTestId("ssh-key-unlock-Layout key")).toBeVisible()
    await expect(page.getByTestId("ssh-key-delete-Layout key")).toBeVisible()
    await page.setViewportSize({ width: 1280, height: 900 })
    for (const mode of ["new", "import"] as const) {
      await page.getByTestId(`ssh-key-${mode}`).click()
      const frame = page.getByRole("dialog", { name: mode === "new" ? "New SSH key" : "Import an SSH key", exact: true })
      expect(Math.abs((await footer.boundingBox())!.height - footerHeight)).toBeLessThanOrEqual(1)
      const before = await frame.boundingBox()
      await frame.getByRole("textbox", { name: "Name", exact: true }).fill("Layout example")
      const name = await page.getByTestId("ssh-key-name").boundingBox()
      const label = await frame.getByText("Name", { exact: true }).boundingBox()
      if (!name || !label) throw new Error("Missing name field")
      expect(label.x + label.width).toBeLessThan(name.x)
      expect(name.height).toBeLessThanOrEqual(36)
      if (mode === "import") {
        await page.getByTestId("ssh-key-file").setInputFiles({
          name: "example.pem", mimeType: "text/plain", buffer: Buffer.from("Example key text"),
        })
        await expect(page.getByTestId("ssh-key-private")).toHaveValue("Example key text")
      }
      await page.getByTestId("ssh-key-passphrase").fill("example passphrase")
      await expect(frame.getByRole("combobox", { name: "The passphrase", exact: true })).toBeVisible()
      expect(await frame.boundingBox()).toEqual(before)
      if (mode === "new") {
        await page.getByTestId("ssh-key-save").click()
        await expect(page.getByTestId("ssh-key-passphrase")).toHaveAttribute("aria-invalid", "true")
        expect(await frame.boundingBox()).toEqual(before)
      }
      await frame.screenshot({ path: `test-results/ssh-${mode}-${theme}.png` })
      await page.setViewportSize({ width: 390, height: 600 })
      await expect(page.getByTestId("ssh-key-save")).toBeInViewport()
      await expect.poll(() => frame.locator(".app-form").evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
      await frame.screenshot({ path: `test-results/ssh-${mode}-${theme}-narrow.png` })
      await frame.getByRole("button", { name: "Cancel", exact: true }).click()
      expect(Math.abs((await footer.boundingBox())!.height - footerHeight)).toBeLessThanOrEqual(1)
      await page.setViewportSize({ width: 1280, height: 900 })
    }
    await page.getByTestId("ssh-key-unlock-Layout key").click()
    const unlock = page.getByRole("dialog", { name: "Unlock Layout key", exact: true })
    await expect(unlock.getByRole("combobox", { name: "Keep it open for", exact: true })).toBeVisible()
    await page.getByTestId("unlock-key-passphrase").fill("example passphrase")
    await page.setViewportSize({ width: 390, height: 600 })
    await expect(page.getByTestId("unlock-key-confirm")).toBeInViewport()
    await unlock.screenshot({ path: `test-results/ssh-unlock-${theme}-narrow.png` })
    await unlock.getByRole("button", { name: "Cancel", exact: true }).click()
  })
}
