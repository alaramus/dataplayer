import { expect, test } from "@playwright/test"
import type { Locator, Page } from "@playwright/test"

import { catalogAction, catalogCheck, catalogRow, openNode, pickSchema } from "./utils/catalog"
import {
  choosePolicy,
  chooseTabColor,
  createFileConnector,
  createPostgresConnector,
} from "./utils/connectors"
import { login } from "./utils/login"
import { toast } from "./utils/notices"
import {
  catalogTab,
  deleteConnector,
  editConnector,
  openConnector,
} from "./utils/workspace"

/**
 * A query document, end to end.
 *
 * What no unit test can show: that the console is a panel of this workspace,
 * that a draft survives a reload because the server holds it, and that
 * deleting one removes it after confirmation (D160). There is no Run in this
 * slice — the document is the whole subject.
 */

async function openQueries(page: Page, connector: string) {
  // The command lives in the bar at the foot of the screen and belongs to the
  // connection being read, so the connection is opened first (D69). It arrives
  // in the library as its filter; the pick below is what a person would do to
  // change it, and here it only asserts the same thing twice cheaply.
  await openConnector(page, connector)
  await page.getByTestId("command-queries").click()
  await page.getByTestId("queries-connector").click()
  await page.getByRole("option", { name: connector, exact: true }).click()
}

async function typeQuery(page: Page, sql: string) {
  await page.locator(".cm-content").click()
  await page.keyboard.press("ControlOrMeta+a")
  await page.keyboard.type(sql)
}

test("writes a query document, names it, and finds it again after a reload", async ({
  page,
}) => {
  const name = `e2e-query-${Date.now()}`
  // Named per run: the library is a person's whole library, and a document
  // left behind by an earlier run is exactly what a search must not confuse
  // this one with.
  const title = `Daily counts ${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openQueries(page, name)

  // --- a new console is in its own tab and in nothing else -----------------
  await page.getByTestId("new-query").click()
  await expect(page.getByTestId("query-state")).toHaveCount(0)
  await expect(page.getByTestId("query-context")).toContainText(name)
  // Nothing on the server to read again, so nothing offers to: the press used
  // to ask for the document that does not exist yet and be told the id it
  // sent is not a UUID.
  await expect(page.getByTestId("query-bar").getByTestId("panel-reload")).toHaveCount(0)

  await typeQuery(page, "select 1 as answer")
  // Still nothing in the library: what a person opened and closed leaves no
  // row behind (D65).
  await expect(page.getByTestId("queries-empty")).toBeVisible()

  // --- keeping it is one press, and names it what the box says -------------
  await page.getByTestId("query-title").fill(title)
  const rememberSize = await page.getByTestId("query-remember").evaluate((button) => ({
    width: button.getBoundingClientRect().width,
    height: button.getBoundingClientRect().height,
  }))
  await page.getByTestId("query-remember").click()
  await expect(page.getByTestId("query-remember")).toContainText("Remembered")
  await expect(page.getByTestId("query-remember")).toBeDisabled()
  expect(await page.getByTestId("query-remember").evaluate((button) => ({
    width: button.getBoundingClientRect().width,
    height: button.getBoundingClientRect().height,
  }))).toEqual(rememberSize)
  await expect(page.getByTestId("query-state")).toHaveCount(0)
  await expect(page.getByTestId("query-bar").getByTestId("panel-reload")).toHaveCount(0)
  // The tab takes the name, because a tab is what a person looks for.
  await expect(page.locator('[data-testid^="workspace-tab-query:"]')).toContainText(title)

  // --- the text is the server's, not the browser's -------------------------
  await page.reload()
  await expect(page.locator(".cm-content")).toContainText("select 1 as answer")
  await expect(page.getByTestId("query-title")).toHaveValue(title)

  // --- and the library finds it by what is written in it -------------------
  await page.getByTestId("queries-search").fill(title)
  const row = page.locator('[data-testid^="query-row-"]')
  await expect(row).toHaveCount(1)
  await expect(row).toContainText(title)

  // --- deletion asks once and removes the stored document -----------------
  await row.locator('[data-testid^="delete-query-"]').click()
  await page.getByTestId("confirm-cancel").click()
  await expect(row).toContainText(title)
  await row.locator('[data-testid^="delete-query-"]').click()
  await page.getByTestId("confirm-accept").click()
  await expect(page.locator('[data-testid^="workspace-tab-query:"]')).toHaveCount(0)
  await expect(page.getByTestId("queries-empty")).toBeVisible()

  await deleteConnector(page, name)
})

test("a query outlives the connection it was written against", async ({ page }) => {
  /** D63: losing the context does not lose the work. */
  const name = `e2e-query-orphan-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openQueries(page, name)
  await page.getByTestId("new-query").click()
  await typeQuery(page, "select 'kept'")
  await page.getByTestId("query-remember").click()
  await expect(page.getByTestId("query-remember")).toContainText("Remembered")
  await expect(page.getByTestId("query-remember")).toBeDisabled()
  await expect(page.getByTestId("query-state")).toHaveCount(0)

  await deleteConnector(page, name)
  await page.reload()

  await expect(page.locator(".cm-content")).toContainText("select 'kept'")
  await expect(page.getByTestId("query-context")).toContainText("Connection unavailable")
})


test("runs the statement under the caret, then the whole script", async ({ page }) => {
  const name = `e2e-run-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openQueries(page, name)
  await page.getByTestId("new-query").click()

  // --- one statement, from the keyboard ------------------------------------
  await typeQuery(page, "select 41 + 1 as answer")
  await page.keyboard.press("ControlOrMeta+Enter")

  const outcome = page.getByTestId("run-outcome")
  await expect(outcome).toBeVisible()
  await expect(page.getByTestId("run-statement-0")).toContainText("succeeded")
  await expect(page.getByTestId("grid-cell-0-0")).toHaveText("42")

  // --- several, only when the command says so ------------------------------
  await typeQuery(page, "select 1 as one;\nselect 2 as two")
  await page.getByTestId("query-run-script").click()
  await expect(page.getByTestId("run-statement-1")).toBeVisible()
  await page.getByTestId("run-statement-1").click()
  await expect(page.getByTestId("grid-cell-0-0")).toHaveText("2")

  // --- an error is an output, not a toast that disappears -------------------
  await typeQuery(page, "select * from nothing_here")
  await page.getByTestId("query-run").click()
  await expect(page.getByTestId("run-error")).toContainText("nothing_here")

  // --- and what the run said is in one chronological place -----------------
  await page.getByTestId("run-messages-tab").click()
  await expect(page.getByTestId("run-messages")).toContainText("MISSING_OBJECT")

  await deleteConnector(page, name)
})

test("keeps the editor and results visible when the query panel is narrowed", async ({ page }) => {
  const name = `e2e-query-narrow-${Date.now()}`
  await page.setViewportSize({ width: 1800, height: 900 })
  await login(page)
  await createPostgresConnector(page, name)
  await openQueries(page, name)
  await page.getByTestId("new-query").click()

  const frame = page.getByTestId("query-frame")
  const editorPane = page.getByTestId("query-editor-pane")
  const editor = editorPane.getByRole("textbox")
  const results = page.getByTestId("query-results-pane")
  const split = page.getByTestId("query-split")
  const rectangle = async (locator: Locator) => {
    const box = await locator.boundingBox()
    if (box === null) throw new Error("The query panel element has no rectangle")
    return box
  }
  const resizeWidth = async (width: number) => {
    const before = await rectangle(frame)
    const grip = await rectangle(page.getByTestId("workspace-separator").last())
    const x = grip.x + grip.width / 2
    const y = grip.y + grip.height / 2
    await page.mouse.move(x, y)
    await page.mouse.down()
    await page.mouse.move(x + before.width - width, y, { steps: 10 })
    await page.mouse.up()
  }
  const expectBothPanes = async () => {
    await expect(editor).toBeVisible()
    await expect(results.getByTestId("grid-cell-0-0")).toBeVisible()
    await expect(split).toBeVisible()
    const upper = await rectangle(editorPane)
    const lower = await rectangle(results)
    const bounds = await rectangle(frame)
    expect(upper.height).toBeGreaterThan(100)
    expect(lower.height).toBeGreaterThan(100)
    expect(upper.y + upper.height).toBeLessThanOrEqual(lower.y)
    expect(lower.y + lower.height).toBeLessThanOrEqual(bounds.y + bounds.height + 1)
  }

  await editor.fill("select 42 as answer")
  await page.keyboard.press("ControlOrMeta+Enter")
  await expect(results.getByTestId("grid-cell-0-0")).toHaveText("42")
  const wide = await rectangle(frame)
  expect(wide.width).toBeGreaterThan(640)
  await expectBothPanes()

  // A narrower column keeps the same vertical split and the live result.
  await resizeWidth(400)
  await expect.poll(async () => (await rectangle(frame)).width).toBeLessThan(640)
  await expectBothPanes()

  const before = await rectangle(editorPane)
  const grip = await rectangle(split)
  await page.mouse.move(grip.x + grip.width / 2, grip.y + grip.height / 2)
  await page.mouse.down()
  await page.mouse.move(grip.x + grip.width / 2, grip.y - 70, { steps: 10 })
  await page.mouse.up()
  await expect.poll(async () => (await rectangle(editorPane)).height)
    .toBeLessThan(before.height - 50)

  // Running again at this width must not replace the editor with its output.
  await editor.fill("select 43 as answer")
  await page.keyboard.press("ControlOrMeta+Enter")
  await expect(results.getByTestId("grid-cell-0-0")).toHaveText("43")
  await expectBothPanes()
  // What survives a change of width is the share of the frame, not a height in
  // pixels: the panes are flexed by the stored fraction, and the chrome above
  // the frame takes one line more in a narrow column, so the frame itself is
  // shorter there.
  const share = async () => {
    const upper = await rectangle(editorPane)
    const lower = await rectangle(results)
    return upper.height / (upper.height + lower.height)
  }
  const narrowed = await share()

  await resizeWidth(wide.width)
  await expect.poll(async () => (await rectangle(frame)).width).toBeGreaterThan(640)
  await expectBothPanes()
  expect(await share()).toBeCloseTo(narrowed, 3)
  await deleteConnector(page, name)
})

test("asks for the values a query needs, and keeps the ones it is told to", async ({
  page,
}) => {
  const name = `e2e-parameters-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openQueries(page, name)
  await page.getByTestId("new-query").click()

  await typeQuery(page, "select count(*) from generate_series(1, 10) i where i > :from_here")
  await expect(page.getByTestId("parameter-from_here")).toBeVisible()
  // Nothing to run until the question is answered.
  await expect(page.getByTestId("query-run")).toBeDisabled()

  await page.getByTestId("parameter-value-from_here").fill("7")
  await page.getByTestId("parameter-remember-from_here").click()

  // A value is kept with the document, and a console is not one until somebody
  // says to keep it (D63), so the reload below would prove nothing without
  // this. Being kept is a rename of the tab and not a new one: the answer
  // already typed into it is still there afterwards.
  await page.getByTestId("query-remember").click()
  await expect(page.getByTestId("query-remember")).toContainText("Remembered")
  await expect(page.getByTestId("query-remember")).toBeDisabled()
  await expect(page.getByTestId("query-state")).toHaveCount(0)
  await expect(page.getByTestId("parameter-value-from_here")).toHaveValue("7")

  await page.getByTestId("query-run").click()
  await expect(page.getByTestId("grid-cell-0-0")).toHaveText("3")

  // The value was remembered with the document, so a reload brings it back.
  await page.reload()
  await expect(page.getByTestId("parameter-value-from_here")).toHaveValue("7")

  await deleteConnector(page, name)
})

test("a captured result is paged, ordered and opened in a panel of its own", async ({
  page,
}) => {
  const name = `e2e-result-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await editConnector(page, name)
  await chooseTabColor(page, "#246abc")
  await page.getByTestId("save-connector").click()
  await openQueries(page, name)
  await page.getByTestId("new-query").click()
  await expect(page.locator('[data-testid^="workspace-tab-query:draft:"]')).toHaveCSS(
    "background-color", "rgb(36, 106, 188)"
  )

  await typeQuery(page, "select i from generate_series(1, 12) i")
  await page.getByTestId("query-run").click()
  await expect(page.getByTestId("grid-cell-0-0")).toHaveText("1")

  // Ordering acts on the captured rows and needs no second execution.
  await page.getByTestId("grid-sort-direction-0").click()
  await expect(page.getByTestId("grid-cell-0-0")).toHaveText("1")
  await page.getByTestId("grid-sort-direction-0").click()
  await expect(page.getByTestId("grid-cell-0-0")).toHaveText("12")

  // And the result can leave the console for a tab of its own (D65).
  await page.getByTestId("run-promote").click()
  await expect(page.locator('[data-testid^="workspace-tab-result:"]')).toHaveCount(1)
  await expect(page.locator('[data-testid^="workspace-tab-result:"]')).toHaveCSS(
    "background-color", "rgb(36, 106, 188)"
  )

  await deleteConnector(page, name)
})


test("history keeps what ran, opens it again and can be deleted", async ({ page }) => {
  const name = `e2e-history-${Date.now()}`
  const marker = `select 'history-${Date.now()}' as kept`
  await login(page)
  await createPostgresConnector(page, name)
  await openQueries(page, name)
  await page.getByTestId("new-query").click()
  await typeQuery(page, marker)
  await page.getByTestId("query-run").click()
  await expect(page.getByTestId("run-statement-0")).toContainText("succeeded")

  // --- what ran is in history, by what was written in it -------------------
  await page.getByTestId("queries-place-history").click()
  await page.getByTestId("queries-search").fill(marker)
  const row = page.locator('[data-testid^="history-row-"]')
  await expect(row).toHaveCount(1)
  await expect(row).toContainText("succeeded")

  // --- and it opens again as a console of its own --------------------------
  await row.locator('[data-testid^="history-restore-"]').click()
  await expect(page.locator('[data-testid^="workspace-tab-query:"]')).toHaveCount(2)

  // --- deleting a run leaves nothing behind --------------------------------
  await row.locator('[data-testid^="history-delete-"]').click()
  await expect(page.getByTestId("history-empty")).toBeVisible()

  await deleteConnector(page, name)
})

test("a captured page can be charted where it is", async ({ page }) => {
  const name = `e2e-chart-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openQueries(page, name)
  await page.getByTestId("new-query").click()
  await typeQuery(page, "select i, i * 2 as doubled from generate_series(1, 5) i")
  await page.getByTestId("query-run").click()
  await expect(page.getByTestId("grid-cell-0-0")).toHaveText("1")

  await page.getByTestId("result-chart").click()

  // The same bounded chart the grid has, over the rows on screen (D35).
  await expect(page.getByTestId("chart-type")).toBeVisible()
  await expect(page.locator("canvas, svg").first()).toBeVisible()

  await page.getByTestId("result-chart-close").click()
  await expect(page.getByTestId("grid-cell-0-0")).toHaveText("1")

  await deleteConnector(page, name)
})


test("the source writes the first query, completes the next and formats both", async ({
  page,
}) => {
  const name = `e2e-intelligence-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "projects")

  // --- the source writes a bounded SELECT about its own table --------------
  await page.getByTestId("grid-query").click()
  const editor = page.locator(".cm-content")
  await expect(editor).toContainText("SELECT")
  await expect(editor).toContainText('"demo_lab"."projects"')
  await expect(editor).toContainText("LIMIT 100")

  // --- completion offers what the source said it has -----------------------
  await editor.click()
  await page.keyboard.press("ControlOrMeta+a")
  await page.keyboard.type("select * from demo_lab.pr")
  // The schema was named in the text, so the console asked the source about
  // it; the next letter typed is answered from what came back (D65).
  await page.waitForTimeout(2000)
  await page.keyboard.type("o")
  const options = page.locator(".cm-tooltip-autocomplete")
  await expect(options).toContainText("demo_lab.projects")
  await page.keyboard.press("Escape")

  // --- and a relation that is not there is a warning, never a red line -----
  await page.keyboard.press("ControlOrMeta+a")
  await page.keyboard.type("select * from demo_lab.no_such_table")
  await expect(page.locator(".cm-lintRange-warning").first()).toBeVisible({
    timeout: 15000,
  })

  // --- formatting is the source's own layout, in one undo ------------------
  await page.keyboard.press("ControlOrMeta+a")
  await page.keyboard.type("select id,name from demo_lab.projects where id=1")
  await page.getByTestId("query-format").click()
  await expect(editor).toContainText("SELECT")
  await page.keyboard.press("ControlOrMeta+z")
  await expect(editor).toContainText("select id,name")

  await deleteConnector(page, name)
})

test("keeps the row of commands still while the connection is being read", async ({
  page,
}) => {
  const name = `e2e-query-bar-${Date.now()}`
  await login(page)
  // Narrow enough that the row has no room to spare, which is where a note
  // taking its own width was paid for by the buttons rather than by the text.
  await page.setViewportSize({ width: 1024, height: 720 })
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "projects")

  // Hold the read of what the connection holds open, so the note the console
  // shows while it waits is on screen long enough to measure. Nothing else
  // waits on it: it is about what completion knows, not about the document.
  await page.route("**/api/v1/queries/connectors/*/metadata", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 4000))
    await route.continue()
  })

  await page.getByTestId("grid-query").click()

  // Measured with every command drawn: the source is asked what it offers, and
  // a row missing Explain and Format is a row with room the real one lacks.
  await expect(page.getByTestId("query-explain")).toBeVisible()
  await expect(page.getByTestId("query-format")).toBeVisible()
  await expect(page.getByTestId("query-knowledge")).toBeVisible()
  const waiting = await page.getByTestId("query-bar").boundingBox()
  const runWaiting = await page.getByTestId("query-run").boundingBox()

  await expect(page.getByTestId("query-knowledge")).toHaveCount(0)
  const read = await page.getByTestId("query-bar").boundingBox()
  const runRead = await page.getByTestId("query-run").boundingBox()

  // The row keeps its height, which is what somebody watching it sees. What
  // says why is the button: the note gave way instead of being paid for out of
  // the commands, which used to slide and then wrap their labels onto a second
  // line for as long as the first read lasted.
  expect(waiting?.height).toBe(read?.height)
  expect(runWaiting?.x).toBe(runRead?.x)
  expect(runWaiting?.width).toBe(runRead?.width)

  await deleteConnector(page, name)
})

test("plans a statement without running it, in three views of one selection", async ({
  page,
}) => {
  const name = `e2e-explain-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openQueries(page, name)
  await page.getByTestId("new-query").click()
  await typeQuery(page, "select * from demo_lab.projects order by name limit 5")

  await page.getByTestId("query-explain").click()

  const explain = page.getByTestId("explain-view")
  await expect(explain).toBeVisible()
  // A plan is estimates, and the screen says so rather than letting the
  // numbers look like measurements.
  await expect(explain).toContainText("nothing was run")
  await expect(page.getByTestId("explain-node-0")).toContainText("Limit")
  await expect(page.getByTestId("explain-node-0.0.0")).toContainText("Seq Scan")

  // --- one selection, three views ------------------------------------------
  await page.getByTestId("explain-node-0.0.0").click()
  await expect(page.getByTestId("explain-details")).toContainText("Seq Scan")
  await page.getByTestId("explain-table").click()
  await expect(page.getByTestId("explain-details")).toContainText("Seq Scan")
  await page.getByTestId("explain-raw").click()
  await expect(page.getByTestId("explain-raw-plan")).toContainText("Seq Scan")

  // --- and it never became a run -------------------------------------------
  await page.getByTestId("explain-close").click()
  await expect(page.getByTestId("query-nothing-run")).toBeVisible()

  await deleteConnector(page, name)
})

/**
 * A row nothing else in the fixture owns.
 *
 * Written into `demo_lab.tags`, and the organisation is looked up rather than
 * numbered: the fixture is rebuilt with generated keys, so 1 is a guess.
 */
function insertTag(label: string): string {
  return (
    `insert into demo_lab.tags (organization_id, label) ` +
    `select min(organization_id), '${label}' from demo_lab.organizations`
  )
}

function countTag(label: string): string {
  return `select count(*) as n from demo_lab.tags where label = '${label}'`
}

test("the connection policy confirms writes and auto-commit keeps what ran", async ({
  page,
}) => {
  const name = `e2e-write-${Date.now()}`
  const label = `e2e-w-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openQueries(page, name)
  await page.getByTestId("new-query").click()

  // --- the connector's confirm policy asks at the run itself --------------
  await typeQuery(page, insertTag(label))
  await page.getByTestId("query-run").click()
  await expect(page.getByTestId("confirm-accept")).toBeVisible()
  await page.getByTestId("confirm-accept").click()

  // --- the confirmed statement goes through, and stays --------------------
  await expect(page.getByTestId("run-no-rows")).toContainText("INSERT")

  await typeQuery(page, countTag(label))
  await page.getByTestId("query-run").click()
  await expect(page.getByTestId("grid-cell-0-0")).toHaveText("1")

  // --- a script that changes something is asked about first (D66) ----------
  await typeQuery(page, `delete from demo_lab.tags where label = '${label}';
${countTag(label)}`)
  await page.getByTestId("query-run-script").click()
  await expect(page.getByTestId("confirm-accept")).toBeVisible()
  await page.getByTestId("confirm-accept").click()

  await page.getByTestId("run-statement-1").click()
  await expect(page.getByTestId("grid-cell-0-0")).toHaveText("0")

  await deleteConnector(page, name)
})

test("a console follows the connection it is open on", async ({ page }) => {
  const name = `e2e-follow-${Date.now()}`
  const renamed = `${name}-renamed`
  await login(page)
  await createPostgresConnector(page, name)
  await openQueries(page, name)
  await page.getByTestId("new-query").click()

  await typeQuery(page, insertTag(`e2e-follow-tag-${Date.now()}`))

  // The owner closes writing while this console is open, and nothing in the
  // console is touched afterwards: either it is told, or it goes on judging
  // the connection by a policy it no longer has (D66).
  await editConnector(page, name)
  await choosePolicy(page, "Read only")
  await page.getByTestId("save-connector").click()
  await page.getByTestId("query-run").click()
  await expect(toast(page, "reading only")).toBeVisible()

  // The policy changes back while the same console remains open.
  await editConnector(page, name)
  await choosePolicy(page, "Ask before writing")
  await page.getByTestId("connector-name").fill(renamed)
  await page.getByTestId("save-connector").click()

  await page.getByTestId("query-run").click()
  await expect(page.getByTestId("confirm-accept")).toBeVisible()
  await page.getByTestId("confirm-cancel").click()

  await deleteConnector(page, renamed)
})

test("a transaction says what it has done, and closing the console rolls it back", async ({
  page,
}) => {
  const name = `e2e-tx-${Date.now()}`
  const label = `e2e-t-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)

  // --- how far a console may go is the connection's own setting ------------
  await editConnector(page, name)
  await choosePolicy(page, "Writing allowed")
  await page.getByTestId("save-connector").click()

  await openQueries(page, name)
  await page.getByTestId("new-query").click()

  // --- manual transaction is a transaction choice, not a write unlock -----
  await expect(page.getByTestId("query-manual-transaction")).toContainText("Manual: Off")
  const manualSize = await page.getByTestId("query-manual-transaction").evaluate((button) => ({
    width: button.getBoundingClientRect().width,
    height: button.getBoundingClientRect().height,
  }))
  await page.getByTestId("query-manual-transaction").hover()
  await expect(page.getByText("Changes commit after each run")).toBeVisible()
  await page.getByTestId("query-manual-transaction").click()
  await expect(page.getByTestId("query-manual-transaction")).toContainText("Manual: On")
  expect(await page.getByTestId("query-manual-transaction").evaluate((button) => ({
    width: button.getBoundingClientRect().width,
    height: button.getBoundingClientRect().height,
  }))).toEqual(manualSize)
  await page.getByTestId("query-manual-transaction").hover()
  await expect(page.getByText("Changes wait for Commit or Roll back")).toBeVisible()

  // --- the bar is the commit preview: what it did, and how long it has -----
  await typeQuery(page, insertTag(label))
  await page.getByTestId("query-run").click()
  await expect(page.getByTestId("transaction-bar")).toContainText("1 changing statement")
  await expect(page.getByTestId("transaction-bar")).toContainText("demo_lab.tags")
  await expect(page.getByTestId("transaction-countdown")).toContainText("Rolls back in")

  await page.getByTestId("transaction-rollback").click()
  await expect(page.getByTestId("transaction-bar")).toBeHidden()

  // --- and rolling back left nothing behind --------------------------------
  await typeQuery(page, countTag(label))
  await page.getByTestId("query-run").click()
  await expect(page.getByTestId("grid-cell-0-0")).toHaveText("0")
  // Reading in this mode opened a transaction of its own, which is what the
  // cross now has to reckon with.
  await expect(page.getByTestId("transaction-bar")).toBeVisible()

  // --- the tab does not take an open transaction away quietly (D66) --------
  const cross = page.locator('[data-testid^="workspace-close-query:"]')
  await cross.click()
  await page.getByTestId("confirm-cancel").click()
  await expect(page.getByTestId("transaction-bar")).toBeVisible()

  await cross.click()
  await page.getByTestId("confirm-accept").click()
  await expect(page.locator('[data-testid^="workspace-tab-query:"]')).toHaveCount(0)

  await deleteConnector(page, name)
})


test("a structure change is tried out first, and the catalog follows it", async ({
  page,
}) => {
  const name = `e2e-ddl-${Date.now()}`
  const table = `e2e_t_${Date.now()}`
  const view = `e2e_v_${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)

  // --- the catalog is open beside the console, showing the schema ----------
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openQueries(page, name)
  await page.getByTestId("new-query").click()

  // --- every structure change is asked about, even a harmless one (D66) ----
  await typeQuery(page, `create table demo_lab.${table} (id int primary key)`)
  await page.getByTestId("query-run").click()
  await expect(page.getByTestId("confirm-accept")).toBeVisible()
  await page.getByTestId("confirm-accept").click()
  await expect(page.getByTestId("run-no-rows")).toContainText("CREATE TABLE")

  // --- the catalog shares the middle column with the query list, and it was
  //     kept alive behind it: coming back to it shows the new table without
  //     anybody asking for a reload
  await catalogTab(page).click()
  await expect(catalogRow(page, table)).toBeVisible()

  // --- and with the catalog in front, the next change lands in it live -----
  await typeQuery(page, `create view demo_lab.${view} as select id from demo_lab.${table}`)
  await page.getByTestId("query-run").click()
  await page.getByTestId("confirm-accept").click()
  await expect(catalogRow(page, view)).toBeVisible()

  // --- what a cascade would take is the database's own answer, read before
  //     the question is answered (D66)
  await typeQuery(page, `drop table demo_lab.${table} cascade`)
  await page.getByTestId("query-run").click()
  await expect(page.getByTestId("confirm-accept")).toBeVisible()
  await expect(page.getByTestId("confirm-message")).toContainText(view)
  await page.getByTestId("confirm-accept").click()

  await expect(catalogRow(page, table)).toBeHidden()
  await expect(catalogRow(page, view)).toBeHidden()

  await deleteConnector(page, name)
})

test("what the editor will not change is refused before anything runs", async ({
  page,
}) => {
  const name = `e2e-nodl-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openQueries(page, name)
  await page.getByTestId("new-query").click()

  await typeQuery(page, "grant select on demo_lab.tags to public")
  await page.getByTestId("query-run").click()
  await page.getByTestId("confirm-accept").click()

  await expect(
    toast(page, "Permissions")
  ).toBeVisible()

  await deleteConnector(page, name)
})


test("runs SQL over the files of a personal directory", async ({ page }) => {
  // The samples come from `docker compose exec backend python -m app.seed_storage`.
  // A second source running SQL is the whole point of D77: the console, the
  // documents and the results were built once and know no adapter name.
  const name = `e2e-file-sql-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)
  await openQueries(page, name)
  await page.getByTestId("new-query").click()

  // --- a file is a relation, named the way the catalog names it ------------
  await typeQuery(page, 'select count(*) as rows from "sample.csv"')
  await page.getByTestId("query-run").click()
  await expect(page.getByTestId("run-statement-0")).toContainText("succeeded")
  await expect(page.getByTestId("grid-cell-0-0")).toHaveText("250")

  // --- two of them, one inside a folder, in one statement ------------------
  await typeQuery(
    page,
    'select q.quarter, (select count(*) from "sample.csv") as cities' +
      ' from "reports/q3.csv" q'
  )
  await page.getByTestId("query-run").click()
  await expect(page.getByTestId("grid-cell-0-0")).toHaveText("Q3")
  await expect(page.getByTestId("grid-cell-0-1")).toHaveText("250")

  // --- the source writes the statement, and there is no writing mode -------
  await expect(page.getByTestId("query-manual-transaction")).toHaveCount(0)

  // --- what it will not do, it says before anything runs -------------------
  await typeQuery(page, 'delete from "sample.csv"')
  await page.getByTestId("query-run").click()
  await expect(
    toast(page, "does not change them through SQL")
  ).toBeVisible()

  // --- and a name that leaves the directory is refused by the one rule -----
  // The whole run is refused rather than one statement, so the answer belongs
  // to the run and is shown above the statements.
  await typeQuery(page, 'select * from "../../../etc/passwd"')
  await page.getByTestId("query-run").click()
  await expect(page.getByTestId("run-refusal")).toContainText("no file called")

  await deleteConnector(page, name)
})

test("opens a log as a table and queries all its lines from the grid", async ({ page }) => {
  const stamp = Date.now()
  const name = `e2e-log-sql-${stamp}`
  const filename = `query-${stamp}.log`
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)

  await catalogAction(page, "upload")
  await page.getByTestId("action-file").setInputFiles({
    name: filename,
    mimeType: "text/plain",
    buffer: Buffer.from(
      "2026-09-04 12:00:00 INFO ready\n".repeat(125) +
      "2026-09-04 12:00:01 ERROR failed\n".repeat(25)
    ),
  })
  await page.getByTestId("action-submit").click()
  await expect(catalogRow(page, filename)).toBeVisible()

  await openNode(page, filename)
  await expect(page.getByTestId("content-editor")).toContainText("INFO ready")
  await page.getByTestId("content-view-table").click()
  await expect(page.getByTestId("row-grid")).toContainText("level")
  await expect(page.getByTestId("grid-cell-0-message")).toHaveText("ready")
  await page.getByTestId("grid-query").click()

  const consolePanel = page.locator(".query-panel")
  const editor = consolePanel.locator(".cm-content")
  await expect(editor).toContainText(`FROM "${filename}"`)
  await expect(editor).toContainText("LIMIT 100")
  await editor.click()
  await page.keyboard.press("ControlOrMeta+a")
  await page.keyboard.type(
    `SELECT level, count(*) AS n FROM "${filename}" GROUP BY level ORDER BY level`
  )
  await consolePanel.getByTestId("query-run").click()
  await expect(consolePanel.getByTestId("run-statement-0")).toContainText("succeeded")
  await expect(consolePanel.getByTestId("grid-cell-0-0")).toHaveText("ERROR")
  await expect(consolePanel.getByTestId("grid-cell-0-1")).toHaveText("25")
  await expect(consolePanel.getByTestId("grid-cell-1-0")).toHaveText("INFO")
  await expect(consolePanel.getByTestId("grid-cell-1-1")).toHaveText("125")
  await expect(consolePanel.getByTestId("query-manual-transaction")).toHaveCount(0)

  await catalogCheck(page, filename).click()
  await catalogAction(page, "delete")
  await page.getByTestId("action-submit").click()
  await expect(catalogRow(page, filename)).toHaveCount(0)
  await deleteConnector(page, name)
})
