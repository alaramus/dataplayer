import type { Page } from "@playwright/test"

/**
 * Reaching the parts of the catalog column.
 *
 * The catalog is a list of one level: a row is opened by clicking it and
 * picked out by its tick box, and everything that can be done to what is
 * picked lives in one menu in the head.
 */
export function catalogRow(page: Page, label: string) {
  return page.getByTestId(`catalog-node-${label}`)
}

export function catalogCheck(page: Page, label: string) {
  return page.getByTestId(`catalog-check-${label}`)
}

/** Open a row: a directory is walked into, anything readable opens a tab. */
export async function openNode(page: Page, label: string) {
  await catalogRow(page, label).click()
}

export async function catalogAction(page: Page, action: string) {
  await page.getByTestId("catalog-actions").click()
  await page.getByTestId(`menu-item-${action}`).click()
}

/** Which groupings the list is showing, for a source that has any. */
export async function pickSchema(page: Page, schema: string) {
  await page.getByTestId("catalog-groups").click()
  await page.getByRole("option", { name: schema, exact: true }).click()
  // The menu stays open for a multiple select: it is closed the way a user
  // closes it, by pressing Escape.
  await page.keyboard.press("Escape")
}

/**
 * Swap one grouping for another in a single visit to the menu.
 *
 * Two calls to `pickSchema` do not do this: the first tick re-reads the list
 * underneath the open menu, and the second visit races the re-render.
 */
export async function showOnlySchema(page: Page, on: string, off: string) {
  await page.getByTestId("catalog-groups").click()
  await page.getByRole("option", { name: on, exact: true }).click()
  await page.getByRole("option", { name: off, exact: true }).click()
  await page.keyboard.press("Escape")
}

/** Add one server-side filter entirely through the visible grid controls. */
export async function addFilter(
  page: Page,
  column: string,
  operator: string,
  value: string,
  expectRows = true
) {
  const editor = page.getByTestId("grid-filter-editor")
  if (!(await editor.isVisible())) await page.getByTestId("grid-filter").click()

  await editor.getByLabel("Column").click()
  await page.getByRole("option", { name: column, exact: true }).click()
  await editor.getByLabel("Operator").click()
  await page.getByRole("option", { name: operator, exact: true }).click()

  const valueField = editor.getByLabel("Value")
  if ((await valueField.getAttribute("role")) === "combobox") {
    await valueField.click()
    await page.getByRole("option", { name: value, exact: true }).click()
  } else {
    await valueField.fill(value)
  }
  const fetched = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" && response.url().endsWith("/fetch")
  )
  await editor.getByTestId("grid-filter-apply").click()
  await fetched
  await editor.waitFor({ state: "visible" })
  if (expectRows) {
    await page.getByTestId(/^grid-cell-0-/).first().waitFor({ state: "visible" })
  } else {
    await page.getByTestId("grid-empty").waitFor({ state: "visible" })
  }
}

export async function sortColumn(page: Page, name: string, shift = false) {
  const fetched = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" && response.url().endsWith("/fetch")
  )
  await page
    .getByTestId(`grid-sort-direction-${name}`)
    .click({ modifiers: shift ? ["Shift"] : [] })
  await fetched
  await page.getByTestId(`grid-sort-priority-${name}`).waitFor({ state: "visible" })
}

export async function selectRange(
  page: Page,
  fromColumn: string,
  fromRow: number,
  toColumn: string,
  toRow: number
) {
  const from = page.getByTestId(`grid-cell-${fromRow}-${fromColumn}`)
  const to = page.getByTestId(`grid-cell-${toRow}-${toColumn}`)
  await from.hover()
  await page.mouse.down()
  await to.hover()
  await page.mouse.up()
}

/** Drag the column's right edge by a measured number of pixels. */
export async function resizeColumn(page: Page, name: string, delta: number) {
  const handle = page.getByTestId(`grid-resize-${name}`)
  const box = await handle.boundingBox()
  if (box === null) throw new Error(`the ${name} resize handle has no box`)
  const x = box.x + box.width / 2
  const y = box.y + box.height / 2
  await page.mouse.move(x, y)
  await page.mouse.down()
  await page.mouse.move(x + delta, y, { steps: 8 })
  await page.mouse.up()
}

export async function pinColumn(page: Page, name: string) {
  await page.getByTestId(`grid-column-select-${name}`).click()
  await page.getByTestId(`grid-pin-${name}`).click()
}
