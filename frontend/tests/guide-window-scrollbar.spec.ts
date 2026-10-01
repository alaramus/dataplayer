import { expect, test } from "@playwright/test"

import { login } from "./utils/login"

/**
 * The frame's resize handles hang outside the window rather than over its
 * edge: a scrollbar drawn at the content's edge keeps the press, and the
 * strip just past the border still resizes (D132).
 */
test("the guide scrollbar keeps the press inside the window, resizing outside", async ({ page }) => {
  await login(page)
  await page.getByTestId("add-connector").click()
  await page.getByTestId("adapter-postgres").click()
  await page.getByTestId("adapter-guide").click()

  const guide = page.getByTestId("guide-window")
  await expect(guide.getByTestId("guide-text")).toBeVisible()

  const hit = await guide.evaluate((window) => {
    const body = window.querySelector<HTMLElement>(".guide-window__body")
    if (body === null) throw new Error("the guide window has no scrolling body")
    if (body.scrollHeight <= body.clientHeight) {
      throw new Error("the guide body does not overflow")
    }
    const box = body.getBoundingClientRect()
    const middle = box.top + box.height / 2
    const at = (x: number) => {
      const hit = document.elementFromPoint(x, middle)
      if (hit === body) return "scrollbar"
      if (hit instanceof HTMLElement && hit.dataset.testid?.startsWith("window-resize")) {
        return "resize"
      }
      return "content"
    }
    return {
      atLane: at(box.right - 2),
      outside: at(box.right + 4),
    }
  })

  // The bar at the content's edge belongs to the scrolling body.
  expect(hit.atLane).toBe("scrollbar")
  // The strip past the border still resizes the window.
  expect(hit.outside).toBe("resize")
})
