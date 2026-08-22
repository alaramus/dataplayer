import { expect, test } from "@playwright/test"

/**
 * The engine is exercised on its own route with placeholder panels: nothing
 * here touches a connector, so a failure is a failure of the layout and not of
 * the data behind it.
 */

test("resizes, collapses and remembers the layout", async ({ page }) => {
  await page.goto("/workspace-demo")

  const alpha = page.getByTestId("workspace-leaf-left")
  const before = (await alpha.boundingBox())?.width ?? 0
  expect(before).toBeGreaterThan(0)

  const separator = page.getByTestId("workspace-separator").first()
  const box = await separator.boundingBox()
  if (box === null) throw new Error("the separator has no box")
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2 + 120, box.y + box.height / 2, { steps: 10 })
  await page.mouse.up()

  const after = (await alpha.boundingBox())?.width ?? 0
  expect(after).toBeGreaterThan(before + 50)

  await page.reload()
  const restored = (await alpha.boundingBox())?.width ?? 0
  expect(Math.abs(restored - after)).toBeLessThan(6)

  await page.getByTestId("workspace-collapse-left").click()
  expect((await alpha.boundingBox())?.width ?? 0).toBeLessThan(40)

  await page.getByTestId("reset-workspace").click()
  expect((await alpha.boundingBox())?.width ?? 0).toBeGreaterThan(50)
})

test("opens a panel as a tab and closes it again", async ({ page }) => {
  await page.goto("/workspace-demo")
  await page.getByTestId("reset-workspace").click()

  await page.getByTestId("open-demo-panel").click()
  const tab = page.getByTestId("workspace-tab-demo-1")
  await expect(tab).toBeVisible()

  await page.getByTestId("workspace-close-demo-1").click()
  await expect(tab).toHaveCount(0)
})
