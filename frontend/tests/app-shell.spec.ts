import { expect, test } from "@playwright/test"

import { login } from "./utils/login"
import { openAdmin } from "./utils/people"
import { chooseTheme } from "./utils/theme"

test("administration and preferences keep the workspace fill shell and footer height", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await login(page)

  for (const theme of ["light", "dark"] as const) {
    await chooseTheme(page, theme)
    const footer = page.getByTestId("app-footer")
    const workspaceHeight = (await footer.boundingBox())!.height
    const railWidth = (await page.getByTestId("tool-rail-left-top").boundingBox())!.width

    await openAdmin(page)
    for (const route of ["admin", "preferences"] as const) {
      const content = page.getByTestId("app-page")
      const surface = page.getByTestId(`${route}-page-surface`)
      const header = page.getByTestId("app-header")
      const body = await content.boundingBox()
      const surfaceBox = await surface.boundingBox()
      const top = await header.boundingBox()
      const bottom = await footer.boundingBox()
      expect(body).not.toBeNull()
      expect(surfaceBox).not.toBeNull()
      expect(top).not.toBeNull()
      expect(bottom).not.toBeNull()
      expect(Math.abs(body!.x)).toBeLessThan(1)
      expect(Math.abs(body!.width - 1280)).toBeLessThan(1)
      expect(Math.abs(surfaceBox!.x - body!.x - railWidth)).toBeLessThan(1)
      expect(Math.abs(surfaceBox!.width - body!.width + 2 * railWidth)).toBeLessThan(1)
      expect(Math.abs(surfaceBox!.height - body!.height)).toBeLessThan(1)
      expect(Math.abs(body!.y - top!.y - top!.height)).toBeLessThan(1)
      expect(Math.abs(body!.y + body!.height - bottom!.y)).toBeLessThan(1)
      expect(Math.abs(bottom!.height - workspaceHeight)).toBeLessThanOrEqual(1)
      await expect(content).toHaveCSS("border-top-width", "0px")
      await expect(content).toHaveCSS("border-top-left-radius", "0px")
      await expect(surface).toHaveCSS("border-top-width", "1px")
      await expect(surface).toHaveCSS("border-top-left-radius", "8px")
      expect(await surface.evaluate((node) => getComputedStyle(node).backgroundColor)).toBe(
        await surface.evaluate((node) => {
          const probe = document.createElement("div")
          probe.style.background = "var(--dp-surface)"
          node.append(probe)
          const color = getComputedStyle(probe).backgroundColor
          probe.remove()
          return color
        })
      )

      if (route === "admin") {
        await page.getByTestId("new-user").click()
        await expect(page.getByRole("dialog", { name: "New user" })).toBeVisible()
        expect(Math.abs((await footer.boundingBox())!.height - workspaceHeight)).toBeLessThanOrEqual(1)
        await page.getByTestId("user-cancel").click()
        expect(Math.abs((await footer.boundingBox())!.height - workspaceHeight)).toBeLessThanOrEqual(1)
        await page.getByTestId("user-menu").click()
        await page.getByTestId("menu-item-preferences").click()
        await page.waitForURL("/preferences")
      }
    }
    await page.getByTestId("back-to-workspace").click()
    await page.waitForURL("/")
  }
})

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
