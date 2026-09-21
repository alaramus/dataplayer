import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { login } from "./utils/login"

// Nothing is started here: every scene ends on Cancel. The real starts are in
// services.spec.ts, which needs the minutes a container takes.
async function openStart(page: Page, template: "postgres" | "ssh") {
  await page.getByTestId("add-connector").click()
  await page.getByTestId(`adapter-${template}`).click()
  await page.getByTestId(`start-service-${template}`).click()
  const content = page.getByTestId("start-service-dialog")
  await expect(content).toBeVisible()
  return { content, frame: page.getByRole("dialog").filter({ has: content }) }
}

async function chooseMode(page: Page, name: string) {
  await page.getByTestId("service-mode").click()
  await page.getByRole("option", { name, exact: true }).click()
  await expect(page.getByRole("listbox")).toHaveCount(0)
}

async function controlX(page: Page, testId: string) {
  return page.getByTestId(testId).evaluate((el) => {
    const control = el.closest(".q-field")?.querySelector(".q-field__control")
    if (!control) throw new Error("Missing field control")
    return control.getBoundingClientRect().x
  })
}

for (const theme of ["light", "dark"] as const) {
  test(`start-service form keeps its size across both ways of asking in ${theme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme })
    await login(page)
    const { content, frame } = await openStart(page, "postgres")
    const before = await frame.boundingBox()
    await expect(page.getByTestId("service-automatic-summary")).toBeVisible()

    // The mode decides how many questions there are; the window stays put (D132).
    await chooseMode(page, "Let me choose")
    await expect(page.getByTestId("service-automatic-summary")).toHaveCount(0)
    expect(await frame.boundingBox()).toEqual(before)
    for (const [id, name] of [["service-name", "Name"], ["service-user", "User"],
      ["service-database", "Database"], ["service-port", "Port"], ["service-password", "Password"]] as const) {
      const field = page.getByTestId(id)
      await expect(field).toHaveAccessibleName(name)
      const label = await frame.getByText(name, { exact: true }).boundingBox()
      const box = await field.boundingBox()
      if (!label || !box) throw new Error(`Missing ${name}`)
      expect(label.x + label.width).toBeLessThan(box.x)
      expect(box.height).toBeLessThanOrEqual(36)
    }
    await expect(page.getByTestId("service-user")).toHaveAttribute("placeholder", "Optional")
    await expect(page.getByTestId("service-user")).toHaveAttribute("autocomplete", "off")
    await expect(page.getByTestId("service-password")).toHaveAttribute("autocomplete", "new-password")
    await expect(frame.getByText("On this machine; 0 lets this server pick a free one", { exact: true })).toBeVisible()
    expect(await page.getByTestId("service-sample-data").boundingBox().then((box) => box?.x))
      .toBeCloseTo(await controlX(page, "service-name"), 0)

    await page.getByTestId("service-password").fill("short")
    await expect(page.getByTestId("service-password")).toHaveAttribute("aria-invalid", "true")
    await expect(page.getByTestId("start-service-confirm")).toBeDisabled()
    expect(await frame.boundingBox()).toEqual(before)
    const body = content.locator(".window-dialog__content")
    expect(await body.evaluate((el) => el.scrollHeight <= el.clientHeight)).toBe(true)
    await frame.screenshot({ path: `test-results/start-service-${theme}.png` })

    await page.setViewportSize({ width: 390, height: 600 })
    await expect.poll(async () => {
      const label = await frame.getByText("Name", { exact: true }).boundingBox()
      const field = await page.getByTestId("service-name").boundingBox()
      return label && field ? field.y - label.y - label.height : -1
    }).toBeGreaterThanOrEqual(0)
    await expect.poll(() => content.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
    await expect(page.getByTestId("start-service-confirm")).toBeInViewport()
    await frame.screenshot({ path: `test-results/start-service-${theme}-narrow.png` })
    await body.evaluate((el) => { el.scrollTop = el.scrollHeight })
    await expect(page.getByTestId("service-sample-data")).toBeInViewport()
    await expect(page.getByTestId("start-service-confirm")).toBeInViewport()
    await frame.getByRole("button", { name: "Cancel", exact: true }).click()
    await expect(content).toHaveCount(0)

    // A server signed into with a key asks one question more than it answers.
    await page.setViewportSize({ width: 1280, height: 720 })
    const ssh = await openStart(page, "ssh")
    const sshBefore = await ssh.frame.boundingBox()
    await chooseMode(page, "Let me choose")
    await page.getByTestId("service-sign-in").click()
    await page.getByRole("option", { name: "One of my SSH keys", exact: true }).click()
    await expect(page.getByRole("listbox")).toHaveCount(0)
    await expect(page.getByTestId("service-password")).toHaveCount(0)
    await expect(ssh.frame.getByRole("combobox", { name: "Your SSH key", exact: true })).toBeVisible()
    expect(await ssh.frame.boundingBox()).toEqual(sshBefore)
    const sshBody = ssh.content.locator(".window-dialog__content")
    expect(await sshBody.evaluate((el) => el.scrollHeight <= el.clientHeight)).toBe(true)
    await ssh.frame.screenshot({ path: `test-results/start-service-ssh-${theme}.png` })
    await ssh.frame.getByRole("button", { name: "Cancel", exact: true }).click()
  })
}
