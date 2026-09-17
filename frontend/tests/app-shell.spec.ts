import { expect, test } from "@playwright/test"

import { login } from "./utils/login"
import { chooseTheme } from "./utils/theme"

test("the workspace meets the shell without an enclosing frame or inset", async ({ page }) => {
  await login(page)
  const content = page.getByTestId("app-page")
  const header = page.getByTestId("app-header")
  const footer = page.getByTestId("app-footer")

  for (const width of [1280, 768]) {
    await page.setViewportSize({ width, height: 800 })
    for (const theme of ["light", "dark"] as const) {
      await chooseTheme(page, theme)
      const chrome = await header.evaluate((node) => getComputedStyle(node).backgroundColor)
      await expect(footer).toHaveCSS("background-color", chrome)
      await expect(content).toHaveCSS("border-top-width", "0px")
      await expect(content).toHaveCSS("border-top-left-radius", "0px")
      await expect(content).toHaveCSS("background-color", chrome)

      // The filling page goes edge to edge: the side rails stand flush
      // against the window, and the sections take everything between them.
      await expect.poll(async () => {
        const bodyBox = await content.boundingBox()
        const headerBox = await header.boundingBox()
        const footerBox = await footer.boundingBox()
        const workspaceBox = await page.getByTestId("workspace").boundingBox()
        const rails: Record<string, { x: number; y: number; width: number; height: number } | null> = {}
        for (const zone of ["left-top", "left-bottom", "right-top", "right-bottom"]) {
          rails[zone] = await page.getByTestId(`tool-rail-${zone}`).boundingBox()
        }
        const leftTop = rails["left-top"]
        const leftBottom = rails["left-bottom"]
        const rightTop = rails["right-top"]
        const rightBottom = rails["right-bottom"]
        if (!bodyBox || !headerBox || !footerBox || !workspaceBox
          || !leftTop || !leftBottom || !rightTop || !rightBottom) return false
        const leftEdge = Math.max(leftTop.x + leftTop.width, leftBottom.x + leftBottom.width)
        const rightEdge = Math.min(rightTop.x, rightBottom.x)
        return Math.abs(bodyBox.x) < 1
          && Math.abs(bodyBox.width - width) < 1
          && Math.abs(workspaceBox.x - leftEdge) < 1
          && Math.abs(workspaceBox.x + workspaceBox.width - rightEdge) < 1
          && Math.abs(workspaceBox.y - bodyBox.y) < 1
          && Math.abs(workspaceBox.height - bodyBox.height) < 1
          && Math.abs(bodyBox.y - headerBox.y - headerBox.height) < 1
          && Math.abs(bodyBox.y + bodyBox.height - footerBox.y) < 1
          && Math.abs(leftTop.height - leftBottom.height) < 2
          && Math.abs(rightTop.height - rightBottom.height) < 2
      }).toBe(true)

      // The four tool rails flank the sections: two equal halves a side,
      // transparent, the chrome showing through.
      for (const zone of ["left-top", "left-bottom", "right-top", "right-bottom"]) {
        const rail = page.getByTestId(`tool-rail-${zone}`)
        await expect(rail).toBeVisible()
        await expect(rail).toHaveCSS("background-color", "rgba(0, 0, 0, 0)")
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width)
    }
  }
})

test("a tooltip over the bar at the foot of the screen draws no scrollbar at a zoom that is not a whole number", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 })
  await login(page)
  // Measured on 2026-09-14: at 110 % to 133 % Quasar capped the tooltip of
  // Data at 43 px over 42 px of text, and a scrollbar showed.
  for (const zoom of [1.1, 1.25]) {
    await page.evaluate((value) => { document.documentElement.style.zoom = String(value) }, zoom)
    await page.mouse.move(600, 300)
    await page.getByTestId("space-data").hover()
    const tip = page.locator(".app-tooltip")
    await expect(tip).toContainText("Connections, catalogs")
    await expect(tip).toHaveCSS("overflow-y", "hidden")
    await page.mouse.move(600, 300)
    await expect(tip).toBeHidden()
  }
})
