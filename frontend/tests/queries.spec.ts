import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { catalogAction, catalogCheck, catalogRow, openNode, pickSchema } from "./utils/catalog"
import {
  choosePolicy,
  createFileConnector,
  createPostgresConnector,
} from "./utils/connectors"
import { login } from "./utils/login"
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
 * deleting one is Trash rather than loss (D63, D65). There is no Run in this
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
  await expect(page.getByTestId("query-state")).toHaveText("Not kept")
  await expect(page.getByTestId("query-context")).toContainText(name)

  await typeQuery(page, "select 1 as answer")
  // Still nothing in the library: what a person opened and closed leaves no
  // row behind (D65).
  await expect(page.getByTestId("queries-empty")).toBeVisible()

  // --- keeping it is one press, and names it what the box says -------------
  await page.getByTestId("query-title").fill(title)
  await page.getByTestId("query-remember").click()
  await expect(page.getByTestId("query-state")).toHaveText("Saved")
  await expect(page.getByTestId("query-remember")).toHaveCount(0)
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

  // --- deleting is Trash for thirty days, and Trash gives it back ----------
  await page.getByTestId("query-trash").click()
  await expect(page.locator(".q-notification", { hasText: "Trash" })).toBeVisible()
  await expect(page.locator('[data-testid^="workspace-tab-query:"]')).toHaveCount(0)
  await expect(page.getByTestId("queries-empty")).toBeVisible()

  await page.getByTestId("queries-place-trash").click()
  const trashed = page.locator('[data-testid^="query-row-"]')
  await expect(trashed).toContainText(title)
  await trashed.locator('[data-testid^="restore-query-"]').click()
  await page.getByTestId("queries-place-queries").click()
  await expect(page.locator('[data-testid^="query-row-"]')).toContainText(title)

  // --- and deleting it for good is a second, deliberate step ---------------
  await page.locator('[data-testid^="trash-query-"]').click()
  await page.getByTestId("queries-place-trash").click()
  await page.locator('[data-testid^="purge-query-"]').click()
  await page.getByTestId("confirm-accept").click()
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
  await expect(page.getByTestId("query-state")).toHaveText("Saved")

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
  await openQueries(page, name)
  await page.getByTestId("new-query").click()

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

/** Choose what the console may do, the way the strip above the editor does. */
async function chooseMode(page: Page, label: string) {
  await page.getByTestId("query-mode").click()
  await page.getByRole("option", { name: label, exact: true }).click()
}

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

test("a console reads until somebody unlocks it, and auto-commit keeps what it did", async ({
  page,
}) => {
  const name = `e2e-write-${Date.now()}`
  const label = `e2e-w-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openQueries(page, name)
  await page.getByTestId("new-query").click()

  // --- read-only is where every document starts, and it holds --------------
  await typeQuery(page, insertTag(label))
  await page.getByTestId("query-run").click()
  await expect(
    page.locator(".q-notification", { hasText: "this run is a read" })
  ).toBeVisible()

  // --- leaving it is typing the name of the connection, and only that ------
  await chooseMode(page, "Auto-commit")
  await expect(page.getByTestId("query-unlock")).toBeVisible()
  await page.getByTestId("query-unlock-name").fill("not the name")
  await page.getByTestId("query-unlock-submit").click()
  await expect(page.locator(".q-notification", { hasText: "exactly" })).toBeVisible()

  await page.getByTestId("query-unlock-name").fill(name)
  await page.getByTestId("query-unlock-submit").click()
  await expect(page.getByTestId("query-relock")).toBeVisible()

  // --- and then the same statement goes through, and stays -----------------
  await page.getByTestId("query-run").click()
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

  // Confirmation is where every connection starts, so the console asks for a
  // name before it will write.
  await chooseMode(page, "Auto-commit")
  await expect(page.getByTestId("query-unlock-name")).toBeVisible()

  // The owner closes writing while this console is open, and nothing in the
  // console is touched afterwards: either it is told, or it goes on judging
  // the connection by a policy it no longer has (D66).
  await editConnector(page, name)
  await choosePolicy(page, "Read only")
  await page.getByTestId("save-connector").click()
  await expect(page.getByTestId("query-write-forbidden")).toBeVisible()
  await expect(page.getByTestId("query-unlock")).toHaveCount(0)

  // Opened again, under another name. What has to be typed back is the name
  // the connection has now, because that is the one the server compares with.
  await editConnector(page, name)
  await choosePolicy(page, "Ask before writing")
  await page.getByTestId("connector-name").fill(renamed)
  await page.getByTestId("save-connector").click()

  await expect(page.getByTestId("query-unlock")).toContainText(renamed)
  await page.getByTestId("query-unlock-name").fill(renamed)
  await page.getByTestId("query-unlock-submit").click()
  await expect(page.getByTestId("query-relock")).toBeVisible()

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

  // --- allowed means no name to type, but still a movement one makes ------
  await chooseMode(page, "Transaction")
  await expect(page.getByTestId("query-unlock")).toContainText("will change")
  await page.getByTestId("query-unlock-submit").click()
  await expect(page.getByTestId("query-relock")).toBeVisible()

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
  await chooseMode(page, "Auto-commit")
  await page.getByTestId("query-unlock-name").fill(name)
  await page.getByTestId("query-unlock-submit").click()
  await expect(page.getByTestId("query-relock")).toBeVisible()

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
  await chooseMode(page, "Auto-commit")
  await page.getByTestId("query-unlock-name").fill(name)
  await page.getByTestId("query-unlock-submit").click()

  await typeQuery(page, "grant select on demo_lab.tags to public")
  await page.getByTestId("query-run").click()
  await page.getByTestId("confirm-accept").click()

  await expect(
    page.locator(".q-notification", { hasText: "Permissions" })
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
  await expect(page.getByTestId("query-mode")).toHaveCount(0)

  // --- what it will not do, it says before anything runs -------------------
  await typeQuery(page, 'delete from "sample.csv"')
  await page.getByTestId("query-run").click()
  await expect(
    page.locator(".q-notification", { hasText: "does not change them through SQL" })
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
  await expect(consolePanel.getByTestId("query-mode")).toHaveCount(0)

  await catalogCheck(page, filename).click()
  await catalogAction(page, "delete")
  await page.getByTestId("action-submit").click()
  await expect(catalogRow(page, filename)).toHaveCount(0)
  await deleteConnector(page, name)
})
