import { expect, test } from "@playwright/test"

import { login } from "./utils/login"

// The headless shell Playwright runs by default has no autofill at all; the
// whole browser has, and fills a field through the protocol the way a person
// picking a saved address does.
test.use({ channel: "chromium" })

test("a field the browser fills keeps its height, and the form under it stays still", async ({ page }) => {
  await login(page)
  await page.goto("/admin")
  await page.getByTestId("new-user").click()
  const email = page.getByTestId("user-email")
  const name = page.getByTestId("user-name")
  await expect(email).toBeVisible()
  const centre = async () => {
    const box = (await email.boundingBox())!
    return box.y + box.height / 2
  }
  const emailCentre = await centre()
  const nameTop = (await name.boundingBox())!.y

  const cdp = await page.context().newCDPSession(page)
  // Autofill is not in the protocol types Playwright ships.
  const send = cdp.send.bind(cdp) as unknown as <T>(method: string, params?: object) => Promise<T>
  const { root } = await send<{ root: { nodeId: number } }>("DOM.getDocument", { depth: -1 })
  const { nodeId } = await send<{ nodeId: number }>("DOM.querySelector", {
    nodeId: root.nodeId,
    selector: '[data-testid="user-email"]',
  })
  const { node } = await send<{ node: { backendNodeId: number } }>("DOM.describeNode", { nodeId })
  await send("Autofill.trigger", {
    fieldId: node.backendNodeId,
    address: { fields: [{ name: "EMAIL_ADDRESS", value: "someone@example.com" }] },
  })

  await expect(email).toHaveValue("someone@example.com")
  expect(await email.evaluate((input) => input.matches(":-webkit-autofill"))).toBe(true)
  // Quasar insets an autofilled input by a pixel either side; the form grew
  // around it by two and moved everything under the field.
  expect(await centre()).toBe(emailCentre)
  expect((await name.boundingBox())!.y).toBe(nameTop)

  await page.getByRole("dialog", { name: "New user" }).getByRole("button", { name: "Cancel" }).click()
})
