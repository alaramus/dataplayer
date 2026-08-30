import { expect } from "@playwright/test"
import type { Locator } from "@playwright/test"

/**
 * Assert what CSS alone is meant to guarantee: an action beside a Quasar
 * field is centred on its control, not on the control plus the message line
 * reserved below it.
 *
 * The field is found by its user-facing test id. Quasar places that id on the
 * native input, so the control is reached through semantic label ancestry
 * rather than by coupling this check to one of Quasar's CSS class names.
 */
export async function expectFieldActionAligned(field: Locator, action: Locator) {
  const fieldMiddle = await field.evaluate((native) => {
    const inner = native.closest("label")?.firstElementChild
    const control = inner?.firstElementChild
    if (!(control instanceof HTMLElement)) return null
    const box = control.getBoundingClientRect()
    return box.y + box.height / 2
  })
  const actionBox = await action.boundingBox()

  expect(fieldMiddle, "the field control was laid out").not.toBeNull()
  expect(actionBox, "the companion action was laid out").not.toBeNull()
  expect(Math.abs((actionBox?.y ?? 0) + (actionBox?.height ?? 0) / 2 - (fieldMiddle ?? 0))).toBeLessThan(
    1
  )
}
