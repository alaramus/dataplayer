import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

/**
 * What Quasar draws on its own, held to the scale (D187).
 *
 * The unit tests read what a component's style says; these read what the
 * browser paints, because every rule here is a component of Quasar's that no
 * `.vue` file of ours writes a size or a colour for: a banner, a table's
 * cells, the line under a field, a compact field, a disabled button, a toggle,
 * a <code>. The showcase renders the real kit and needs no backend.
 */

async function openShowcase(page: Page, theme: "light" | "dark") {
  await page.addInitScript((value) => localStorage.setItem("dataplayer-theme", value), theme)
  await page.goto("/ui-kit")
  await expect(page.locator(".q-banner").first()).toBeVisible()
  await expect(page.locator("body.body--dark")).toHaveCount(theme === "dark" ? 1 : 0)
}

/** A token as the browser resolves it, so a colour is compared with a colour. */
async function token(page: Page, name: string): Promise<string> {
  return page.evaluate((property) => {
    const probe = document.createElement("span")
    probe.style.color = `var(${property})`
    document.body.appendChild(probe)
    const value = getComputedStyle(probe).color
    probe.remove()
    return value
  }, name)
}

for (const theme of ["light", "dark"] as const) {
  test(`holds Quasar's own components to the scale in ${theme}`, async ({ page }) => {
    await openShowcase(page, theme)
    const text = await token(page, "--dp-text")
    const muted = await token(page, "--dp-text-muted")

    // A banner's message is the body's 13px at the body's spacing, its icon a
    // control's 20px.
    const banner = page.locator(".q-banner").first()
    const message = await banner.locator(".q-banner__content").evaluate((node) => {
      const style = getComputedStyle(node)
      return { size: style.fontSize, spacing: style.letterSpacing }
    })
    expect(message).toEqual({ size: "13px", spacing: "normal" })
    expect(await banner.locator(".q-icon").first().evaluate((node) => getComputedStyle(node).fontSize)).toBe("20px")

    // A table's cells read in the body's colour, not Quasar's #000 or #fff.
    const cell = page.locator(".app-table tbody td").first()
    expect(await cell.evaluate((node) => getComputedStyle(node).color)).toBe(text)

    // The line under a field wraps at 16px and is the muted colour.
    const bottom = page.getByTestId("kit-hinted-field").locator("xpath=ancestor::label[1]").locator(".q-field__bottom")
    const hint = await bottom.evaluate((node) => ({
      colour: getComputedStyle(node).color,
      line: getComputedStyle(node.querySelector(".q-field__messages") ?? node).lineHeight,
    }))
    expect(hint).toEqual({ colour: muted, line: "16px" })

    // Every compact field stands at a control's height, a select included.
    const heights = await page.locator(".app-select--compact .q-field__control, .app-input--compact .q-field__control")
      .evaluateAll((nodes) => nodes.map((node) => Math.round(node.getBoundingClientRect().height)))
    expect(heights.length).toBeGreaterThan(2)
    expect(new Set(heights)).toEqual(new Set([32]))

    // A main action that cannot be pressed is not a grey button of its own.
    const disabled = page.getByRole("button", { name: "disabled", exact: true })
    const enabled = page.locator(".q-btn.bg-dp-action-primary:not(.disabled)").first()
    const grounds = {
      off: await disabled.evaluate((node) => getComputedStyle(node).backgroundColor),
      on: await enabled.evaluate((node) => getComputedStyle(node).backgroundColor),
      opacity: await disabled.evaluate((node) => getComputedStyle(node).opacity),
    }
    expect(grounds.off).not.toBe(grounds.on)
    expect(grounds.opacity).toBe("1")

    // A toggle's track starts where its row starts.
    const toggle = await page.locator(".q-toggle").first().evaluate((node) => {
      const track = node.querySelector(".q-toggle__track")
      return track === null ? null : Math.round(track.getBoundingClientRect().x - node.getBoundingClientRect().x)
    })
    expect(toggle).toBe(0)

    // Code in the chrome is the application's monospace.
    const face = await page.locator("code").first().evaluate((node) => getComputedStyle(node).fontFamily)
    expect(face.startsWith("ui-monospace")).toBe(true)
  })
}

test("the bar of a scroll area keeps the arrow a native scrollbar has", async ({ page }) => {
  await openShowcase(page, "light")
  const area = page.locator(".app-scroll-area").first()
  await area.hover()
  // Quasar's grab hand stood over this bar and over no other in the
  // application: the rail of a pushed-aside column showed it.
  for (const part of [".q-scrollarea__bar--v", ".q-scrollarea__thumb--v"]) {
    await expect(area.locator(part)).toHaveCSS("cursor", "default")
  }
})
