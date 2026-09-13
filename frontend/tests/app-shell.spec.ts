import { expect, test } from "@playwright/test"

import { login } from "./utils/login"

test("the workspace meets the shell without an enclosing frame or inset", async ({ page }) => {
  await login(page)
  const content = page.getByTestId("app-page")
  const header = page.getByTestId("app-header")
  const footer = page.getByTestId("app-footer")
  const toggle = page.getByTestId("theme-toggle")

  for (const width of [1280, 768]) {
    await page.setViewportSize({ width, height: 800 })
    for (const theme of ["light", "dark"]) {
      if (await toggle.getAttribute("data-theme") !== theme) await toggle.click()
      await expect(toggle).toHaveAttribute("data-theme", theme)
      const chrome = await header.evaluate((node) => getComputedStyle(node).backgroundColor)
      await expect(footer).toHaveCSS("background-color", chrome)
      await expect(content).toHaveCSS("border-top-width", "0px")
      await expect(content).toHaveCSS("border-top-left-radius", "0px")
      await expect(content).toHaveCSS("background-color", chrome)

      await expect.poll(async () => {
        const bodyBox = await content.boundingBox()
        const headerBox = await header.boundingBox()
        const footerBox = await footer.boundingBox()
        const workspaceBox = await page.getByTestId("workspace").boundingBox()
        if (!bodyBox || !headerBox || !footerBox || !workspaceBox) return false
        return bodyBox.x >= 8
          && Math.abs(workspaceBox.x - bodyBox.x) < 1
          && Math.abs(workspaceBox.y - bodyBox.y) < 1
          && Math.abs(workspaceBox.width - bodyBox.width) < 1
          && Math.abs(workspaceBox.height - bodyBox.height) < 1
          && Math.abs(bodyBox.x - (width - bodyBox.x - bodyBox.width)) < 1
          && Math.abs(bodyBox.y - headerBox.y - headerBox.height) < 1
          && Math.abs(bodyBox.y + bodyBox.height - footerBox.y) < 1
      }).toBe(true)

      const rail = await content.evaluate((node) => {
        const bounds = node.getBoundingClientRect()
        const element = document.elementFromPoint(bounds.left / 2, bounds.top + bounds.height / 2)
        return element ? getComputedStyle(element).backgroundColor : null
      })
      expect(rail).toBe(chrome)
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width)
    }
  }
})
