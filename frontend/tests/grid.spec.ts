import { expect, test } from "@playwright/test"

import {
  addFilter,
  openNode,
  pickSchema,
  pinColumn,
  resizeColumn,
  selectRange,
  sortColumn,
} from "./utils/catalog"
import { createFileConnector, createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { chooseTheme } from "./utils/theme"
import { connectorRow, deleteConnector, openConnector } from "./utils/workspace"
import { toast } from "./utils/notices"

test("groups the commands, keeps them all, and says why a greyed one is off", async ({
  page,
}) => {
  const table = `e2e-toolbar-${Date.now()}`
  const file = `e2e-toolbar-file-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, table)
  await openConnector(page, table)
  await pickSchema(page, "demo_lab")
  await openNode(page, "tags")
  await expect(page.getByTestId("grid-page-range")).toContainText("Rows")

  // Five named groups, in the order of a working session. The row is the same
  // row wherever it is opened, so a command keeps the place it was learned in.
  for (const [group, label] of [
    ["view", "The view"],
    ["open", "Read it as"],
    ["out", "Take it out"],
    ["write", "Change the rows"],
    ["tab", "This tab"],
  ]) {
    await expect(page.getByTestId(`grid-group-${group}`)).toContainText(label)
    const caption = page.getByTestId(`grid-group-${group}`).getByText(label, { exact: true })
    await expect(caption).toHaveCSS("text-transform", "none")
    const typography = await caption.evaluate((node) => {
      const style = getComputedStyle(node)
      return { size: parseFloat(style.fontSize), line: parseFloat(style.lineHeight) }
    })
    expect(typography.size).toBeGreaterThanOrEqual(12)
    expect(typography.line).toBeGreaterThan(typography.size)
  }

  // Greyed for want of a selection, and the sentence names what to do about
  // it. Whether a tooltip opens over a disabled button at all is a question
  // about pointer events that only a browser answers.
  await expect(page.getByTestId("grid-delete")).toBeDisabled()
  await page.getByTestId("grid-delete").hover()
  await expect(page.locator(".q-tooltip")).toContainText("tick a row first")

  // How many rows a page holds is a fact about paging, so it sits with the
  // range it changes rather than at the far end of the command row.
  await expect(page.getByTestId("grid-header").getByTestId("grid-page-size")).toHaveCount(0)
  await expect(page.getByTestId("grid-page-size")).toBeVisible()

  // The other kind of greyed: a delimited file does not sort, and no amount of
  // clicking will make it. The command is drawn all the same, in its place.
  await createFileConnector(page, file)
  await openConnector(page, file)
  await openNode(page, "sample.csv")
  await expect(page.getByTestId("grid-page-range")).toContainText("Rows")
  await expect(page.getByTestId("grid-sort")).toBeDisabled()
  await page.getByTestId("grid-sort").hover()
  await expect(page.locator(".q-tooltip")).toContainText("does not sort rows")

  await deleteConnector(page, file)
  await deleteConnector(page, table)
})

test("keeps the column names in sight while their rows scroll away", async ({ page }) => {
  // Geometry, which is the one thing a unit test cannot see: the names used to
  // scroll off the top with the first rows, leaving a page of values with
  // nothing saying what they were.
  const name = `e2e-sticky-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "pg_catalog")
  await openNode(page, "pg_class")
  await expect(page.getByTestId("row-grid")).toContainText("relname")

  const box = page.locator(".data-grid__scroll").first()
  const heading = page.getByTestId("grid-column-relname")
  const before = await heading.boundingBox()
  await box.evaluate((node) => {
    node.scrollTop = 400
  })
  await expect.poll(async () => box.evaluate((node) => node.scrollTop)).toBeGreaterThan(0)

  const after = await heading.boundingBox()
  const top = await box.evaluate((node) => node.getBoundingClientRect().top)
  // Where it was, and where the box begins: it neither moved nor let itself be
  // scrolled under.
  expect(Math.round(after?.y ?? -1)).toBe(Math.round(before?.y ?? -2))
  expect(Math.round(after?.y ?? -1)).toBe(Math.round(top))

  await deleteConnector(page, name)
})

test("keeps the controls of a new row inside their own cell", async ({ page }) => {
  // Three buttons in a column seventy-two pixels wide: the check and the cross
  // were drawn over the column beside them, and only a browser could say so.
  const name = `e2e-insert-fit-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "projects")
  await page.getByTestId("grid-insert").click()

  const cell = await page.locator(".row-insert__selector").boundingBox()
  for (const control of ["save", "paste", "cancel"]) {
    const button = await page.getByTestId(`grid-insert-${control}`).boundingBox()
    expect(button, control).not.toBeNull()
    expect(Math.round(button?.x ?? 0), control).toBeGreaterThanOrEqual(Math.round(cell?.x ?? 0))
    expect(
      Math.round((button?.x ?? 0) + (button?.width ?? 0)),
      control
    ).toBeLessThanOrEqual(Math.round((cell?.x ?? 0) + (cell?.width ?? 0)))
  }

  await page.getByTestId("grid-insert-cancel").click()
  await deleteConnector(page, name)
})

test("keeps rows compact and follows a column drag before release", async ({ page }) => {
  const name = `e2e-grid-density-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "projects")
  const cell = page.getByTestId("grid-cell-0-name")
  await expect(cell).toBeVisible()

  const toolbarButton = (await page.getByTestId("grid-sort").boundingBox())!
  const header = (await page.getByTestId("grid-column-name").boundingBox())!
  expect(header.height).toBeGreaterThan((await cell.boundingBox())!.height)
  for (const id of ["grid-select-page", "grid-sort-direction-name", "grid-pin-name", "grid-hide-name"]) {
    const button = (await page.getByTestId(id).boundingBox())!
    expect(button.height).toBeCloseTo(toolbarButton.height, 0)
    expect(button.width).toBeCloseTo(toolbarButton.width, 0)
    expect(button.y).toBeGreaterThanOrEqual(header.y)
    expect(button.y + button.height).toBeLessThanOrEqual(header.y + header.height)
  }

  // Every row on the page rather than a number: the claim is about how a row
  // is drawn, and the fixture holds two projects.
  const shown = await page.getByTestId(/^grid-row-\d+$/).count()
  expect(shown).toBeGreaterThan(1)
  for (let row = 0; row < shown; row += 1) {
    const dataRow = page.getByTestId(`grid-row-${row}`)
    await dataRow.hover()
    const before = (await dataRow.boundingBox())!
    expect(before.height).toBeLessThanOrEqual(28)
    const action = page.getByTestId(`grid-open-row-${row}`)
    await expect(action).toBeVisible()
    const button = (await action.boundingBox())!
    expect(button.y).toBeGreaterThanOrEqual(before.y)
    expect(button.y + button.height).toBeLessThanOrEqual(before.y + before.height)
    await page.getByTestId("grid-header").hover()
    expect((await dataRow.boundingBox())!.height).toBe(before.height)
  }

  const heading = page.getByTestId("grid-column-name")
  // The column beside it in this relation: widening one must leave the others
  // the width they had.
  const neighbor = page.getByTestId("grid-column-code")
  const originalWidth = (await heading.boundingBox())!.width
  const neighborWidth = (await neighbor.boundingBox())!.width
  // Scrolled to first: the pointer cannot be put outside the viewport, and a
  // drag that starts nowhere leaves the column the width it had.
  await page.getByTestId("grid-resize-name").scrollIntoViewIfNeeded()
  const handle = (await page.getByTestId("grid-resize-name").boundingBox())!
  const x = handle.x + handle.width / 2
  const y = handle.y + handle.height / 2
  await page.mouse.move(x, y)
  await page.mouse.down()
  try {
    for (const delta of [30, 60]) {
      await page.mouse.move(x + delta, y, { steps: 4 })
      await expect.poll(async () => (await heading.boundingBox())!.width)
        .toBeCloseTo(originalWidth + delta, 0)
      expect((await cell.boundingBox())!.width).toBeCloseTo(originalWidth + delta, 0)
      expect((await neighbor.boundingBox())!.width).toBeCloseTo(neighborWidth, 0)
    }
  } finally {
    await page.mouse.up()
  }

  await resizeColumn(page, "name", -500)
  await expect.poll(async () => (await heading.boundingBox())!.width).toBeCloseTo(72, 0)
  expect((await cell.boundingBox())!.width).toBeCloseTo(72, 0)
  await page.getByTestId("grid-resize-name").dblclick()
  await expect.poll(async () => (await heading.boundingBox())!.width)
    .toBeCloseTo(originalWidth, 0)

  await page.reload()
  await expect(heading).toBeVisible()
  expect((await heading.boundingBox())!.width).toBeCloseTo(originalWidth, 0)
  await deleteConnector(page, name)
})

test("explores a relation and restores its view", async ({ page, context }) => {
  const name = `e2e-grid-${Date.now()}`
  await context.grantPermissions(["clipboard-read", "clipboard-write"])
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "projects")

  await addFilter(page, "status", "equals", "active")
  await addFilter(page, "budget", "greater than", "1000")
  await sortColumn(page, "priority")
  await sortColumn(page, "name", true)
  await expect(page.getByTestId("grid-sort-priority-name")).toHaveText("2")

  await page.getByTestId("grid-page-size").click()
  await page.getByRole("option", { name: "250", exact: true }).click()
  await page.getByTestId("grid-columns").click()
  await page.getByRole("checkbox", { name: "priority", exact: true }).click()
  await page.getByRole("checkbox", { name: "status", exact: true }).click()
  await page.getByTestId("grid-columns").click()
  await selectRange(page, "name", 0, "budget", 0)
  await page.getByTestId("grid-copy").click()
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe(
    "Core Platform\t180000.00"
  )

  await resizeColumn(page, "name", 60)
  await pinColumn(page, "name")
  await page.reload()
  const pinned = page.getByTestId("grid-column-name")
  await expect(pinned).toHaveCSS("position", "sticky")
  // And it draws its own edges. A stuck cell cannot use the table's borders -
  // with `border-collapse: collapse` they belong to the table, so they stay
  // behind while the cell travels and its own background covers them, which
  // left the rows sliding under a pinned column with nothing between them.
  // The borders are the cells' now, which is also why each line is drawn once.
  await expect(pinned).toHaveCSS("border-right-width", "1px")
  await expect(page.getByTestId("row-grid").locator("table")).toHaveCSS(
    "border-collapse",
    "separate"
  )
  await expect(page.getByTestId("grid-page-range")).toContainText("Rows 1")
  await page.screenshot({ path: "test-results/grid-desktop.png", fullPage: true })

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("streams every matching row into a CSV download", async ({ page }) => {
  const name = `e2e-grid-export-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "projects")

  await addFilter(page, "status", "equals", "active")
  await page.getByTestId("grid-columns").click()
  await page.getByRole("checkbox", { name: "priority", exact: true }).click()
  await page.getByTestId("grid-columns").click()
  await page.getByTestId("grid-download").click()
  await expect(page.getByTestId("grid-download-dialog")).toContainText(
    "1 active filters"
  )
  await page.getByTestId("download-scope-all").click()

  const started = page.waitForEvent("download")
  await page.getByTestId("grid-download-run").click()
  const download = await started

  expect(download.suggestedFilename()).toMatch(/^projects-.*\.csv$/)
  await expect(
    toast(page, "rows downloaded")
  ).toBeVisible()

  await deleteConnector(page, name)
})

test("recovers from a rejected query without restoring it", async ({ page }) => {
  test.setTimeout(60_000)
  const name = `e2e-grid-query-error-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "projects")
  await expect(page.getByTestId("grid-cell-0-name")).toBeVisible()

  await page.route("**/*", async (route) => {
    const request = route.request()
    if (request.method() !== "POST" || !request.url().includes("/fetch")) {
      await route.continue()
      return
    }
    const body = request.postDataJSON() as { filters?: unknown[] }
    if ((body.filters?.length ?? 0) === 0) {
      await route.continue()
      return
    }
    await route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Query failed" }),
    })
  })

  const applyRejectedFilter = async () => {
    const editor = page.getByTestId("grid-filter-editor")
    if (!(await editor.isVisible())) await page.getByTestId("grid-filter").click()
    await editor.getByLabel("Column").click()
    await page.getByRole("option", { name: "name", exact: true }).click()
    await editor.getByLabel("Operator").click()
    await page.getByRole("option", { name: "equals", exact: true }).click()
    await editor.getByTestId("grid-filter-apply").click()
    const value = editor.getByLabel("Value")
    await expect(value).toHaveAttribute("aria-invalid", "true")
    await expect(value).toHaveAccessibleDescription("Enter a value")
    await expect(editor.getByRole("alert")).toHaveText("Enter a value")
    await editor.getByLabel("Value").fill("rejected")
    await expect(value).not.toHaveAttribute("aria-invalid", "true")
    await expect(value).not.toHaveAttribute("aria-describedby")
    await editor.getByTestId("grid-filter-apply").click()
    // What the server said, not what the screen would say instead of it: a
    // refusal written as a sentence is shown as it stands.
    await expect(page.getByTestId("grid-error")).toContainText("Query failed", {
      timeout: 15_000,
    })
  }

  await applyRejectedFilter()
  await page.getByTestId("grid-reset-query").click()
  await expect(page.getByTestId("grid-cell-0-name")).toBeVisible()

  await applyRejectedFilter()
  await page.reload()
  await expect(page.getByTestId("grid-cell-0-name")).toBeVisible()
  await expect(page.getByTestId("grid-error")).toHaveCount(0)

  await deleteConnector(page, name)
})

test("opens a complete JSON value", async ({ page }) => {
  const name = `e2e-grid-json-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "audit_events")

  await page.getByTestId("grid-cell-0-payload").dblclick()
  await expect(page.getByTestId("grid-viewer")).toContainText('"source"')
  await expect(page.getByTestId("grid-viewer")).toContainText('"success"')
  await expect
    .poll(async () => (await page.getByTestId("grid-viewer").boundingBox())?.width ?? 0)
    .toBeGreaterThan(800)
  await page.screenshot({ path: "test-results/grid-dialog.png", fullPage: true })
  await page.getByRole("button", { name: "Close", exact: true }).click()
  await expect(page.getByTestId("grid-viewer")).toHaveCount(0)

  await deleteConnector(page, name)
})

test("edits one PostgreSQL cell and can write SQL NULL", async ({ page }) => {
  const name = `e2e-grid-edit-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "projects")

  await addFilter(page, "name", "equals", "Signal Research")
  const budget = page.getByTestId("grid-cell-0-budget")
  if ((await budget.textContent()) === "null") {
    await budget.dblclick()
    await page.getByTestId("grid-edit-null").click()
    await page.getByTestId("grid-edit-value").fill("90000.00")
    await page.getByTestId("grid-edit-save").click()
    await expect(budget).toHaveText("90000.00")
  }

  await budget.dblclick()
  await page.getByTestId("grid-edit-null").click()
  await page.getByTestId("grid-edit-save").click()
  await expect(budget).toHaveText("null")

  await budget.dblclick()
  await page.getByTestId("grid-edit-null").click()
  await page.getByTestId("grid-edit-value").fill("90000.00")
  await page.getByTestId("grid-edit-save").click()
  await expect(budget).toHaveText("90000.00")

  await deleteConnector(page, name)
})

test("inserts and deletes a PostgreSQL row", async ({ page }) => {
  const name = `e2e-grid-mutations-${Date.now()}`
  const label = `e2e-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "tags")

  await addFilter(page, "label", "equals", label, false)
  await expect(page.getByTestId("grid-empty")).toBeVisible()
  await page.getByTestId("grid-insert").click()
  await page.getByTestId("grid-insert-value-organization_id").fill("1")
  await page.getByTestId("grid-insert-value-label").fill(label)
  await page.getByTestId("grid-insert-save").click()

  await expect(page.getByTestId("grid-cell-0-label")).toHaveText(label)
  await expect(page.getByTestId("grid-cell-0-color")).toHaveText("#64748B")
  await page.getByTestId("grid-select-row-0").click()
  await expect(page.getByTestId("grid-delete")).toBeEnabled()
  await page.getByTestId("grid-delete").click()
  await page.getByTestId("confirm-accept").click()
  await expect(page.getByTestId("grid-empty")).toBeVisible()

  await deleteConnector(page, name)
})

test("looks a value up in a CSV and still offers it no sorting", async ({ page }) => {
  const name = `e2e-grid-csv-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)
  await openNode(page, "sample.csv")

  // A file has no index to order by (D109), so sorting is greyed — in its
  // place, and saying so on hover, rather than gone. The per-column controls
  // are a different thing and are absent: a column offers no direction to
  // pick when the source will not order by it at all.
  await expect(page.getByTestId("grid-columns")).toBeVisible()
  await expect(page.getByTestId("grid-sort")).toBeDisabled()
  await expect(page.locator('[data-testid^="grid-sort-direction-"]')).toHaveCount(0)

  // Equality is the whole vocabulary it states, and the row it names is on a
  // page a scan had to reach.
  await addFilter(page, "name", "equals", "city-7")
  await expect(page.getByTestId("grid-page-range")).toHaveText("Rows 1–1")
  await expect(page.getByTestId("grid-cell-0-id")).toHaveText("7")

  await deleteConnector(page, name)
})

test("opening the row count menu does not briefly widen the pager", async ({ page }) => {
  const name = `e2e-grid-page-size-width-${Date.now()}`
  await page.setViewportSize({ width: 1440, height: 900 })
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)
  await openNode(page, "sample.csv")
  await expect(page.getByTestId("grid-cell-0-id")).toBeVisible()

  const header = page.getByTestId("grid-pager")
  // A final bounding box misses the bug: the arrow only overflows while it
  // rotates. Record every rendered frame from the click through its transition.
  await header.evaluate((element) => {
    const bar = element
    if (!(bar instanceof HTMLElement)) throw new Error("The pager is missing")
    element.addEventListener("click", () => {
      const baseline = {
        width: bar.clientWidth,
        scrollWidth: bar.scrollWidth,
        height: bar.getBoundingClientRect().height,
      }
      let maxScrollWidth = baseline.scrollWidth
      let maxHeight = baseline.height
      const until = performance.now() + 500
      const sample = () => {
        maxScrollWidth = Math.max(maxScrollWidth, bar.scrollWidth)
        maxHeight = Math.max(maxHeight, bar.getBoundingClientRect().height)
        if (performance.now() < until) {
          requestAnimationFrame(sample)
        } else {
          element.setAttribute("data-menu-dimensions", JSON.stringify({
            baseline, maxScrollWidth, maxHeight,
          }))
        }
      }
      requestAnimationFrame(sample)
    }, { once: true, capture: true })
  })
  await page.getByTestId("grid-page-size").click()
  const option = page.getByRole("option", { name: "50", exact: true })
  await expect(option).toBeVisible()
  await expect.poll(() => header.getAttribute("data-menu-dimensions")).not.toBeNull()
  const dimensions = JSON.parse(await header.getAttribute("data-menu-dimensions") ?? "null") as {
    baseline: { width: number; scrollWidth: number; height: number }
    maxScrollWidth: number
    maxHeight: number
  }
  expect(dimensions.baseline.scrollWidth).toBe(dimensions.baseline.width)
  expect(dimensions.maxScrollWidth).toBe(dimensions.baseline.scrollWidth)
  expect(dimensions.maxHeight).toBe(dimensions.baseline.height)

  await option.click()
  await expect(page.getByTestId("grid-page-range")).toContainText("Rows 1–50")
  await deleteConnector(page, name)
})

test("keeps the grid legible in the dark theme", async ({ page }) => {
  const name = `e2e-grid-dark-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "projects")

  await chooseTheme(page, "dark")
  await expect(page.getByTestId("grid-header")).toBeVisible()
  await expect(page.getByTestId("grid-cell-0-name")).toBeVisible()
  await page.screenshot({ path: "test-results/grid-dark.png", fullPage: true })

  await deleteConnector(page, name)
})

test("keeps a narrow grid header, rows and pager separate", async ({ page }) => {
  const name = `e2e-grid-narrow-${Date.now()}`
  await page.setViewportSize({ width: 900, height: 720 })
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "projects")

  const header = await page.getByTestId("grid-header").boundingBox()
  const cell = await page.getByTestId("grid-cell-0-name").boundingBox()
  const pager = await page.getByTestId("grid-page-range").boundingBox()
  if (header === null || cell === null || pager === null) throw new Error("the grid is not laid out")
  expect(header.y + header.height).toBeLessThanOrEqual(cell.y)
  expect(cell.y + cell.height).toBeLessThanOrEqual(pager.y)
  await page.screenshot({ path: "test-results/grid-narrow.png", fullPage: true })

  await deleteConnector(page, name)
})

test("keeps the 500-row page mode interactive", async ({ page, context }) => {
  const name = `e2e-grid-500-${Date.now()}`
  await context.grantPermissions(["clipboard-read", "clipboard-write"])
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "pg_catalog")
  await openNode(page, "pg_class")

  await page.getByTestId("grid-page-size").click()
  await page.getByRole("option", { name: "500", exact: true }).click()
  await page.getByTestId("grid-cell-0-relname").click()
  await page.getByTestId("grid-copy").click()
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).not.toBe("")
  await sortColumn(page, "relname")
  await expect(page.getByTestId("grid-sort-direction-relname")).toBeVisible()
  await page.getByTestId("grid-page-size").click()
  await page.getByRole("option", { name: "50", exact: true }).click()
  await expect(page.getByTestId("grid-page-range")).toContainText("Rows 1–50")

  await page.getByTestId("grid-next").click()
  await expect(page.getByTestId("grid-page-range")).toContainText("Rows 51–100")

  await page.getByTestId("grid-prev").click()
  await expect(page.getByTestId("grid-page-range")).toContainText("Rows 1–50")

  await deleteConnector(page, name)
})

test("pastes a block of cells and refuses one the column cannot read", async ({
  page,
  context,
}) => {
  const name = `e2e-grid-paste-${Date.now()}`
  const label = `e2e-paste-${Date.now()}`
  const pasted = `${label}-done`
  await context.grantPermissions(["clipboard-read", "clipboard-write"])
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "tags")

  await addFilter(page, "label", "contains", label, false)
  await expect(page.getByTestId("grid-empty")).toBeVisible()
  await page.getByTestId("grid-insert").click()
  await page.getByTestId("grid-insert-value-organization_id").fill("1")
  await page.getByTestId("grid-insert-value-label").fill(label)
  await page.getByTestId("grid-insert-save").click()
  await expect(page.getByTestId("grid-cell-0-label")).toHaveText(label)

  // Two cells at once, landing from the selected one: the block is the app's
  // own TSV, and nothing about it is typed into a form.
  await page.evaluate(
    (text) => navigator.clipboard.writeText(text),
    `${pasted}\t#123456`
  )
  await page.getByTestId("grid-cell-0-label").click()
  await page.getByTestId("grid-paste").click()
  await expect(page.getByTestId("grid-cell-0-label")).toHaveText(pasted)
  await expect(page.getByTestId("grid-cell-0-color")).toHaveText("#123456")

  // A value the column's type cannot read is named, and nothing is written.
  await page.evaluate(() => navigator.clipboard.writeText("not a number"))
  await page.getByTestId("grid-cell-0-organization_id").click()
  await page.getByTestId("grid-paste").click()
  await expect(toast(page, "cannot be read")).toBeVisible()
  // Contains rather than equals: a foreign-key cell also carries the arrow
  // that leads to the row it names.
  const key = page.getByTestId("grid-cell-0-organization_id")
  await expect(key).not.toContainText("not a number")
  await expect(key).toContainText("1")

  await page.getByTestId("grid-select-row-0").click()
  await page.getByTestId("grid-delete").click()
  await page.getByTestId("confirm-accept").click()
  await expect(page.getByTestId("grid-empty")).toBeVisible()

  await deleteConnector(page, name)
})

test("keeps a row in its place when one of its cells is edited", async ({ page }) => {
  const name = `e2e-grid-order-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "app_users")

  // Two rows are enough to tell an order from an accident.
  const first = await page.getByTestId("grid-cell-0-email").textContent()
  const second = await page.getByTestId("grid-cell-1-email").textContent()
  expect(first).not.toBe(second)

  const cell = page.getByTestId("grid-cell-0-full_name")
  const before = (await cell.textContent()) ?? ""
  await cell.dblclick()
  await page.getByTestId("grid-edit-value").fill(`${before} edited`)
  await page.getByTestId("grid-edit-save").click()
  await expect(cell).toHaveText(`${before} edited`)

  // PostgreSQL wrote the changed row somewhere else in the heap; the page is
  // ordered by the key, so the reader does not see it move (D42).
  await expect(page.getByTestId("grid-cell-0-email")).toHaveText(first ?? "")
  await expect(page.getByTestId("grid-cell-1-email")).toHaveText(second ?? "")

  await cell.dblclick()
  await page.getByTestId("grid-edit-value").fill(before)
  await page.getByTestId("grid-edit-save").click()
  await expect(cell).toHaveText(before)

  await deleteConnector(page, name)
})

test("copies a whole row and fills a new one from it", async ({ page, context }) => {
  const name = `e2e-grid-duplicate-${Date.now()}`
  const label = `e2e-dup-${Date.now()}`
  const copy = `${label}-copy`
  await context.grantPermissions(["clipboard-read", "clipboard-write"])
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "tags")

  // One row of our own to copy, so nothing in the fixture is duplicated.
  await addFilter(page, "label", "contains", label, false)
  await page.getByTestId("grid-insert").click()
  await page.getByTestId("grid-insert-value-organization_id").fill("1")
  await page.getByTestId("grid-insert-value-label").fill(label)
  await page.getByTestId("grid-insert-value-color").fill("#ABCDEF")
  await page.getByTestId("grid-insert-save").click()
  await expect(page.getByTestId("grid-cell-0-label")).toHaveText(label)

  // Select the whole row and copy it.
  await page.getByTestId("grid-cell-0-tag_id").click()
  await page.getByTestId("grid-cell-0-color").click({ modifiers: ["Shift"] })
  await page.getByTestId("grid-copy").click()

  // A new row filled from that line: the identity is the source's, so it is
  // named as left out rather than dictated.
  await page.getByTestId("grid-insert").click()
  await page.getByTestId("grid-insert-paste").click()
  await expect(
    toast(page, "Left to the source: tag_id")
  ).toBeVisible()
  await expect(page.getByTestId("grid-insert-value-color")).toHaveValue("#ABCDEF")
  await page.getByTestId("grid-insert-value-label").fill(copy)
  await page.getByTestId("grid-insert-save").click()

  await expect(page.getByTestId("grid-cell-1-label")).toHaveText(copy)
  await expect(page.getByTestId("grid-cell-1-color")).toHaveText("#ABCDEF")

  // One at a time: ticking a row replaces the selection rather than adding to it.
  for (let left = 2; left > 0; left -= 1) {
    await page.getByTestId("grid-select-row-0").click()
    await page.getByTestId("grid-delete").click()
    await page.getByTestId("confirm-accept").click()
    // The page has to be re-read before row 0 is ticked again. Without this
    // the second tick lands on the row still being deleted, and the source
    // correctly refuses to delete it twice.
    await expect(page.getByTestId("row-grid").locator("tbody tr")).toHaveCount(
      left - 1
    )
  }
  await expect(page.getByTestId("grid-empty")).toBeVisible()

  await deleteConnector(page, name)
})

test("brings rows in from a file in personal storage", async ({ page }) => {
  const target = `e2e-import-target-${Date.now()}`
  const source = `e2e-import-source-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, target)
  await createFileConnector(page, source)
  await openConnector(page, target)
  await pickSchema(page, "demo_lab")
  await openNode(page, "tags")

  // Nothing of ours is there yet. By label, because the two the file carries
  // are named uniquely enough that a test running beside this one cannot make
  // them appear.
  await addFilter(page, "label", "equals", "one", false)

  await page.getByTestId("grid-import").click()
  await page.getByTestId("grid-import-source").click()
  await page.getByRole("option", { name: source, exact: true }).click()
  await page.getByTestId("grid-import-node-sample.tsv").click()

  // Each column of this relation stands on its own row, named and typed,
  // against the choice that fills it. A row used to be one select labelled
  // with the column it filled, and a compact select is narrow enough to cut
  // that name down to a single letter.
  const columns = page.getByTestId("grid-import-columns")
  await expect(columns).toContainText("Column in this relation")
  await expect(columns).toContainText("Filled from")
  await expect(page.getByTestId("grid-import-row-organization_id")).toContainText(
    "organization_id"
  )

  // The file's own columns, paired by hand: nothing is matched silently.
  // Every pair offers the same source columns, so a menu still closing from
  // the previous one would swallow the click. Wait for exactly one list.
  const lists = page.getByRole("listbox")
  const pair = async (target: string, source: string) => {
    await expect(lists).toHaveCount(0)
    await page.getByTestId(`grid-import-pair-${target}`).click()
    await expect(lists).toHaveCount(1)
    await page.getByRole("option", { name: source, exact: true }).click()
    await expect(page.getByTestId(`grid-import-pair-${target}`)).toContainText(source)
  }
  await pair("organization_id", "id")
  await pair("label", "name")
  // How much of the relation would be written, said once above the rows: a
  // compact field keeps no room under it for anything.
  await expect(page.getByTestId("grid-import-tally")).toContainText("2 of")

  await page.getByTestId("grid-import-preview").click()
  await expect(page.getByTestId("grid-import-dialog")).toContainText("one")

  await page.getByTestId("grid-import-run").click()
  await expect(
    toast(page, "2 rows brought in")
  ).toBeVisible()

  // The first of them, through the filter that showed nothing a moment ago.
  await expect(page.getByTestId("grid-cell-0-label")).toHaveText("one")
  await page.getByTestId("grid-select-row-0").click()
  await page.getByTestId("grid-delete").click()
  await page.getByTestId("confirm-accept").click()
  await expect(page.getByTestId("grid-empty")).toBeVisible()

  // And the second, which proves both arrived.
  await page.getByTestId("grid-filter-clear").click()
  await addFilter(page, "label", "equals", "two")
  await page.getByTestId("grid-select-row-0").click()
  await page.getByTestId("grid-delete").click()
  await page.getByTestId("confirm-accept").click()
  await expect(page.getByTestId("grid-empty")).toBeVisible()

  await deleteConnector(page, target)
  await deleteConnector(page, source)
})

test("brings rows in from a table through another database connection", async ({ page }) => {
  const target = `e2e-table-import-target-${Date.now()}`
  const source = `e2e-table-import-source-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, target)
  await createPostgresConnector(page, source)
  await openConnector(page, target)
  await pickSchema(page, "demo_lab")
  await openNode(page, "tags")

  await addFilter(page, "label", "equals", "Northstar Labs", false)
  await page.getByTestId("grid-import").click()
  await page.getByTestId("grid-import-source").click()
  await page.getByRole("option", { name: source, exact: true }).click()
  await page.getByTestId("grid-import-node-demo_lab").click()
  await page.getByTestId("grid-import-node-organizations").click()

  const lists = page.getByRole("listbox")
  const pair = async (targetColumn: string, sourceColumn: string) => {
    await expect(lists).toHaveCount(0)
    await page.getByTestId(`grid-import-pair-${targetColumn}`).click()
    await expect(lists).toHaveCount(1)
    await page.getByRole("option", { name: sourceColumn, exact: true }).click()
    await expect(page.getByTestId(`grid-import-pair-${targetColumn}`)).toContainText(
      sourceColumn
    )
  }
  await pair("organization_id", "organization_id")
  await pair("label", "display_name")

  await page.getByTestId("grid-import-preview").click()
  await expect(page.getByTestId("grid-import-dialog")).toContainText("Northstar Labs")
  await page.getByTestId("grid-import-run").click()
  await expect(
    toast(page, "2 rows brought in")
  ).toBeVisible()

  await expect(page.getByTestId("grid-cell-0-label")).toHaveText("Northstar Labs")
  await page.getByTestId("grid-select-row-0").click()
  await page.getByTestId("grid-delete").click()
  await page.getByTestId("confirm-accept").click()
  await expect(page.getByTestId("grid-empty")).toBeVisible()

  await page.getByTestId("grid-filter-clear").click()
  await addFilter(page, "label", "equals", "Blue Orbit")
  await page.getByTestId("grid-select-row-0").click()
  await page.getByTestId("grid-delete").click()
  await page.getByTestId("confirm-accept").click()
  await expect(page.getByTestId("grid-empty")).toBeVisible()

  await deleteConnector(page, target)
  await deleteConnector(page, source)
})

test("re-reads a relation on a timer, and stops when told to", async ({ page }) => {
  const name = `e2e-grid-refresh-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "projects")
  await expect(page.getByTestId("grid-page-range")).toContainText("Rows 1")

  // Counted at the network, because that is the whole claim: the grid asks
  // the source again without anybody pressing anything.
  let reads = 0
  page.on("request", (request) => {
    if (request.url().includes("/fetch") && request.method() === "POST") reads += 1
  })

  const button = page.getByTestId("grid-auto-refresh")
  await button.click()
  await page.getByTestId("menu-item-s1").click()
  await expect(button).toHaveAttribute("data-refresh", "1")
  await expect(button).toContainText("1 s")
  await expect.poll(() => reads, { timeout: 10_000 }).toBeGreaterThanOrEqual(3)

  // The interval belongs to the relation, so it survives a reload.
  await page.reload()
  await expect(page.getByTestId("grid-auto-refresh")).toHaveAttribute("data-refresh", "1")

  await page.getByTestId("grid-auto-refresh").click()
  await page.getByTestId("menu-item-off").click()
  await expect(page.getByTestId("grid-auto-refresh")).toHaveAttribute(
    "data-refresh",
    "off"
  )
  const stopped = reads
  await page.waitForTimeout(2500)
  expect(reads).toBe(stopped)

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})
