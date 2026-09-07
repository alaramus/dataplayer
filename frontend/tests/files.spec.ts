import { expect, test } from "@playwright/test"
import type { Locator } from "@playwright/test"

import { catalogAction, catalogCheck, catalogRow, openNode } from "./utils/catalog"
import { createFileConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { toast } from "./utils/notices"
import {
  catalogTabIcon,
  connectorRow,
  deleteConnector,
  openConnector,
  rowsTabs,
} from "./utils/workspace"

// The samples come from `docker compose exec backend python -m app.seed_storage`:
// this sub-project cannot write files, so a personal directory is empty until
// that script has run.
test("opens a connector draft for one folder and saves only when asked", async ({ page }) => {
  const parent = `e2e-folder-parent-${Date.now()}`
  const child = `e2e-folder-child-${Date.now()}`
  await login(page)
  await createFileConnector(page, parent)
  await openConnector(page, parent)

  await page.getByTestId("catalog-actions").click()
  await expect(page.getByTestId("menu-item-connect_folder")).toHaveAttribute("aria-disabled", "true")
  await page.keyboard.press("Escape")
  await catalogCheck(page, "notes.txt").click()
  await page.getByTestId("catalog-actions").click()
  await expect(page.getByTestId("menu-item-connect_folder")).toHaveAttribute("aria-disabled", "true")
  await page.keyboard.press("Escape")
  await catalogCheck(page, "notes.txt").click()
  await catalogCheck(page, "reports").click()

  await catalogAction(page, "connect_folder")
  await expect(page.getByTestId("connector-name")).toHaveValue("reports")
  // Rooted, the way the folder of a connection is stored and the way the path
  // bar copies it.
  await expect(page.getByTestId("field-path")).toHaveValue("/reports")
  await page.getByTestId("connector-name").fill(child)
  await expect(page.getByTestId("connector-tab-color")).toBeVisible()
  await expect(connectorRow(page, child)).toHaveCount(0)
  await page.getByTestId("cancel-connector").click()
  await expect(connectorRow(page, child)).toHaveCount(0)

  await catalogAction(page, "connect_folder")
  await expect(page.getByTestId("connector-name")).toHaveValue("reports")
  await page.getByTestId("connector-name").fill(child)
  await page.getByTestId("save-connector").click()
  await expect(connectorRow(page, child)).toBeVisible()
  await openConnector(page, child)
  await expect(page.getByTestId("catalog-list")).toContainText("q3.csv")
  await expect(page.getByTestId("catalog-up")).toHaveCount(0)
  await expect(catalogRow(page, "reports")).toHaveCount(0)

  await deleteConnector(page, child)
  await openConnector(page, parent)
  await expect(catalogRow(page, "reports")).toBeVisible()
  await deleteConnector(page, parent)
})

test("copies the path of the level it is standing on", async ({ page, context }) => {
  const name = `e2e-path-${Date.now()}`
  await context.grantPermissions(["clipboard-read", "clipboard-write"])
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)

  // The root is a place like any other, and its path is "/" — the same string
  // its owner would type into the folder of a connection. The server is never
  // named: what is copied begins at the root of this source.
  const path = page.getByTestId("catalog-path")
  const copy = page.getByTestId("catalog-copy-path")
  await path.hover()
  await copy.click()
  await expect
    .poll(() => page.evaluate(() => navigator.clipboard.readText()))
    .toBe("/")

  await openNode(page, "reports")
  const crumb = path.getByRole("button", { name: "reports", exact: true })
  const up = page.getByTestId("catalog-up")
  await up.focus()
  await up.hover()
  await expect(copy).toBeHidden()
  const beforeHover = await crumb.boundingBox()
  expect(beforeHover).not.toBeNull()

  await crumb.hover()
  await expect(copy).toBeVisible()
  expect(await crumb.boundingBox()).toEqual(beforeHover)

  const pathBox = await path.boundingBox()
  const copyBox = await copy.boundingBox()
  const homeBox = await page.getByTestId("catalog-home").boundingBox()
  if (!pathBox || !copyBox || !homeBox) throw new Error("The path controls have no bounds")
  const rightGap = pathBox.x + pathBox.width - copyBox.x - copyBox.width
  expect(rightGap).toBeGreaterThanOrEqual(0)
  expect(rightGap).toBeLessThanOrEqual(6)
  expect(copyBox.height).toBeLessThan(homeBox.height)

  await copy.click()
  await expect
    .poll(() => page.evaluate(() => navigator.clipboard.readText()))
    .toBe("/reports")

  await up.focus()
  await up.hover()
  await expect(copy).toBeHidden()
  await crumb.focus()
  await page.keyboard.press("Tab")
  await expect(copy).toBeFocused()
  await expect(copy).toBeVisible()
  await page.evaluate(() => navigator.clipboard.writeText(""))
  await page.keyboard.press("Enter")
  await expect
    .poll(() => page.evaluate(() => navigator.clipboard.readText()))
    .toBe("/reports")

  await deleteConnector(page, name)
})

test("browses a personal directory and opens each implemented viewer", async ({ page }) => {
  const name = `e2e-files-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)

  await openConnector(page, name)

  const list = page.getByTestId("catalog-list")
  await expect(list).toContainText("reports")
  await expect(list).toContainText("sample.csv")
  await expect(list).toContainText("notes.txt")
  // The size is a caption of the row. Asserted here because a unit test of the
  // mapper passed once while nothing reached the screen.
  await expect(list).toContainText(/\d+(\.\d+)? KB/)

  // The path is always visible for a file source, even at the top.
  await expect(page.getByTestId("catalog-path")).toBeVisible()
  await expect(page.getByTestId("catalog-home")).toBeVisible()

  // A directory is walked into, and the path says where we are.
  await openNode(page, "reports")
  await expect(page.getByTestId("catalog-path")).toContainText("reports")

  // The source icon lives on the tab, not in the head - the head holds
  // the path and the menu on one line.
  await expect(catalogTabIcon(page)).toBeVisible()
  await expect(list).toContainText("q3.csv")

  // The way back is the first row of the list, as it is in any other
  // explorer, rather than a button in the head.
  await expect(list.locator("> div").first()).toHaveAttribute("data-testid", "catalog-up")
  // It lines up with the rows that have a tick box: the space is reserved by
  // the control itself, so nothing here depends on guessing how wide it is.
  const back = await page.getByTestId("catalog-up").getByText("..").boundingBox()
  const beside = await catalogRow(page, "q3.csv").getByText("q3.csv").boundingBox()
  expect(Math.abs((back?.x ?? 0) - (beside?.x ?? 0))).toBeLessThan(1)

  await page.getByTestId("catalog-up").click()
  await expect(list).toContainText("sample.csv")
  await expect(page.getByTestId("catalog-up")).toHaveCount(0)

  // And the path starts at a home button rather than at the name of the
  // connection, which is already on the tab above it.
  await openNode(page, "reports")
  await page.getByTestId("catalog-home").click()
  await expect(list).toContainText("sample.csv")

  await openNode(page, "sample.csv")
  const grid = page.getByTestId("row-grid")
  await expect(grid).toContainText("population")
  await expect(grid.locator("tbody tr")).toHaveCount(100)
  // A file has no row estimate: counting means reading it end to end, so the
  // grid pages without ever claiming a total.
  await expect(grid).toContainText("Rows 1–100")
  await expect(grid).not.toContainText("of ~")

  await page.getByTestId("grid-next").click()
  await expect(grid).toContainText("Rows 101–200")

  // The list is a column of its own, so nothing covered it and nothing had to
  // be clicked to get back to it.
  await openNode(page, "notes.txt")
  await expect(page.getByTestId("content-editor")).toContainText("line 1")
  // A text file has no columns, so nothing offers to read it as rows.
  await expect(page.getByTestId("content-view-table")).toHaveCount(0)

  // An image is checked by the source and opens in its bounded native viewer.
  await openNode(page, "logo.png")
  await expect(page.getByTestId("image-preview")).toBeVisible()
  await expect(page.getByTestId("image-details")).toContainText("PNG")
  await expect(page.getByTestId("image-details")).toContainText("1 × 1")

  // Download belongs to the selected catalog node, not to its viewer.
  await expect(page.getByTestId("content-download-original")).toHaveCount(0)
  await catalogCheck(page, "logo.png").click()
  const downloadStarted = page.waitForEvent("download")
  await catalogAction(page, "download")
  const downloaded = await downloadStarted
  expect(downloaded.suggestedFilename()).toBe("logo.png")

  // A folder is archived even when it is the only selected node.
  await catalogCheck(page, "logo.png").click()
  await catalogCheck(page, "reports").click()
  const folderStarted = page.waitForEvent("download")
  await catalogAction(page, "download")
  expect((await folderStarted).suggestedFilename()).toBe("reports.zip")

  // Several nodes become one archive through the same action.
  await catalogCheck(page, "notes.txt").click()
  const severalStarted = page.waitForEvent("download")
  await catalogAction(page, "download")
  expect((await severalStarted).suggestedFilename()).toBe("download.zip")
  await expect(rowsTabs(page)).toHaveCount(1)

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("opens JSON natively and turns it into a table only when asked", async ({ page }) => {
  const name = `e2e-json-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)

  // Opening the file preserves the document. A number no JavaScript float
  // could hold arrives as its own source text, unrounded.
  await openNode(page, "people.json")
  await expect(page.getByTestId("content-editor")).toContainText("10000000000000001")
  await expect(page.getByTestId("row-grid")).toHaveCount(0)

  // The table is an alternative representation, opened by an explicit act.
  await page.getByTestId("content-view-table").click()
  const grid = page.getByTestId("row-grid")
  await expect(grid).toContainText("name")
  await expect(grid).toContainText("city")
  await expect(grid.locator("tbody tr")).toHaveCount(3)

  // JSONL opens as its own source too, and is still offered as a table.
  await openNode(page, "events.jsonl")
  await expect(page.getByTestId("content-editor")).toContainText("login")
  await expect(page.getByTestId("content-view-table")).toBeVisible()

  // A file named .json that is not JSON opens all the same: the editor holds
  // source, so a document that no parser accepts is exactly what it can fix.
  await openNode(page, "broken.json")
  await expect(page.getByTestId("content-editor")).toContainText('"b" 2')

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

/**
 * Reach a block the way a reader does.
 *
 * Heavy blocks mount when they are scrolled to, so a locator for one does not
 * exist until the document has been scrolled that far. Scrolling until it
 * appears is both how the assertion gets its element and the proof that
 * nothing was drawn before it was needed.
 */
async function scrollTo(document: Locator, testId: string): Promise<Locator> {
  const block = document.getByTestId(testId)
  for (let step = 0; step < 30 && (await block.count()) === 0; step += 1) {
    await document.evaluate((element) => {
      element.scrollBy(0, 300)
    })
    await document.page().waitForTimeout(100)
  }
  return block
}

test("opens Markdown as a document, with its diagram, chart and source", async ({ page }) => {
  const name = `e2e-markdown-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)

  // Opening the file gives the document, not its characters: the heading is a
  // heading and the hashes are gone.
  await openNode(page, "guide.md")
  const rendered = page.getByTestId("markdown-document")
  await expect(rendered.getByRole("heading", { name: "Sample document" })).toBeVisible()
  await expect(rendered).not.toContainText("# Sample document")
  await expect(rendered.locator("table")).toBeVisible()
  await expect(page.getByTestId("content-editor")).toHaveCount(0)

  // Headings form one duplicate-safe outline, and search visits the literal
  // text the reader sees rather than fenced payloads.
  const contents = page.getByTestId("markdown-contents")
  await expect(contents).toContainText("What it renders")
  await contents.getByRole("button", { name: "What it renders" }).click()
  await expect(rendered.locator("#what-it-renders")).toBeFocused()
  await page.getByTestId("markdown-search").fill("document")
  await expect(page.getByTestId("markdown-search-position")).toHaveText(/1\/\d+/)
  await page.getByTestId("markdown-search-next").click()
  await expect(page.getByTestId("markdown-search-position")).toHaveText(/2\/\d+/)
  await page.getByTestId("markdown-search").fill("")

  // A callout an agent wrote is a card, not a listing: its kind is named and
  // its leading key lines are laid out as fields.
  const decision = rendered.getByTestId("agent-decision")
  await expect(rendered.getByTestId("agent-summary")).toContainText("Every block this viewer")
  await expect(decision).toContainText("Keep documents portable Markdown")
  await expect(decision).not.toContainText("Decision:")
  await expect(rendered).not.toContainText("```")

  // Nothing below the fold has been drawn yet.
  await expect(rendered.getByTestId("echarts-figure")).toHaveCount(0)

  // The rich blocks draw as they are reached, each in its own language.
  await expect((await scrollTo(rendered, "mermaid-figure")).locator("svg")).toBeVisible()
  await expect((await scrollTo(rendered, "echarts-figure")).locator("svg")).toBeVisible()
  await expect(await scrollTo(rendered, "code-fence")).toContainText("def total")

  // Every block says what it is and what can be done with it: its source can
  // be copied, and what was drawn can be saved.
  await expect(rendered.getByTestId("mermaid-download")).toBeVisible()
  await expect(rendered.getByTestId("echarts-download")).toBeVisible()
  await expect(rendered.getByTestId("code-copy")).toBeVisible()

  // A drawing can be read as its own source, and shown again.
  await scrollTo(rendered, "svg-figure")
  await rendered.getByTestId("svg-source-toggle").click()
  await expect(rendered.getByTestId("svg-source")).toContainText("<circle")
  await expect(rendered.getByTestId("svg-figure")).toHaveCount(0)
  await rendered.getByTestId("svg-source-toggle").click()
  await expect(rendered.getByTestId("svg-figure").locator("svg")).toBeVisible()

  // A path beside the Markdown is resolved through the catalog, then opened
  // only through the image representation's verified content ticket.
  const localImage = rendered.getByRole("img", { name: "local logo" })
  await localImage.scrollIntoViewIfNeeded()
  await expect(localImage).toHaveAttribute("src", /\/content-files\//)

  // Nothing was fetched from another site, and the document says so.
  await expect(rendered.locator("img[data-remote-blocked]")).toHaveCount(1)
  await expect(page.getByText(/image\(s\) in this document are hosted elsewhere/)).toBeVisible()

  // Export is the rendered document alone, not the workspace around it.
  const download = page.waitForEvent("download")
  await page.getByTestId("markdown-export").click()
  await page.getByTestId("menu-item-html").click()
  expect((await download).suggestedFilename()).toBe("guide.html")

  // The same bytes are one click away in the editor, which is where a
  // document is changed.
  await page.getByTestId("markdown-view-source").click()
  await expect(page.getByTestId("content-editor")).toContainText("# Sample document")
  await expect(page.getByTestId("editor-language")).toHaveText("Markdown")

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("opens a file as its own source and saves an edit back", async ({ page }) => {
  const name = `e2e-editor-${Date.now()}`
  const folder = `editor-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)

  // A folder of this test's own: the samples are shared by every scenario in
  // this file, and one of them asserts what notes.txt still says.
  const list = page.getByTestId("catalog-list")
  await catalogAction(page, "create_folder")
  await page.getByTestId("action-dialog").getByRole("textbox").first().fill(folder)
  await page.getByTestId("action-submit").click()
  await expect(list).toContainText(folder)

  await openNode(page, folder)
  await catalogAction(page, "upload")
  await page.getByTestId("action-file").setInputFiles({
    name: "worker.py",
    mimeType: "text/x-python",
    buffer: Buffer.from("VALUE = 'before'\n"),
  })
  // The picker stages the file; the upload is the button under the list.
  await page.getByTestId("action-submit").click()
  await expect(list).toContainText("worker.py")

  // Opening the file is opening the editor: there is no second mode to reach
  // for, and nothing offers to read a source file as rows.
  await openNode(page, "worker.py")
  const editor = page.getByTestId("content-editor")
  await expect(editor).toContainText("VALUE = 'before'")
  await expect(page.getByTestId("content-view-table")).toHaveCount(0)
  // The language is named by CodeMirror's own metadata, from the filename.
  await expect(page.getByTestId("editor-language")).toHaveText("Python")
  // Nothing has changed yet, so there is nothing to save.
  await expect(page.getByTestId("content-save")).toBeDisabled()

  await editor.locator(".cm-content").click()
  await page.keyboard.press("ControlOrMeta+a")
  await page.keyboard.type("VALUE = 'after'")
  await page.getByTestId("content-save").click()
  await expect(toast(page, "saved")).toBeVisible()

  // The bytes reached the source, not only the browser: a reload re-reads the
  // file, and the tab comes back with what was written.
  await page.reload()
  await expect(page.getByTestId("content-editor")).toContainText("VALUE = 'after'")

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("opens a columnar file and a workbook sheet as datasets", async ({ page }) => {
  const name = `e2e-datasets-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)

  const list = page.getByTestId("catalog-list")
  await expect(list).toContainText("cities.parquet")
  await expect(list).toContainText("budget.xlsx")

  // A columnar file opens as rows whose columns keep the types it declares.
  await openNode(page, "cities.parquet")
  const grid = page.getByTestId("row-grid")
  await expect(grid).toContainText("population")
  await expect(grid.locator("tbody tr")).toHaveCount(100)

  // And it has a structure, because it states its own columns. The facts of
  // the format are shown beside them.
  await page.getByTestId("grid-structure").click()
  const structure = page.getByTestId("structure-view")
  await expect(structure).toContainText("int64")
  const format = page.getByTestId("structure-format")
  await expect(format).toContainText("Parquet")
  await expect(format).toContainText("Row groups")
  // Nothing about a file dataset can be changed, and the screen says so.
  await expect(page.getByTestId("structure-add-column")).toBeDisabled()

  // A workbook opens as its first sheet rather than as a folder to walk into,
  // and the tab it opens switches between the rest along the foot (D51).
  await openConnector(page, name)
  await openNode(page, "budget.xlsx")
  await expect(page.getByTestId("row-grid")).toContainText("quarter")
  const sheets = page.getByTestId("sheet-switcher")
  await expect(sheets.getByTestId("sheet-Revenue")).toHaveAttribute(
    "aria-selected",
    "true"
  )

  await sheets.getByTestId("sheet-People").click()
  await expect(page.getByTestId("row-grid")).toContainText("name")
  await expect(page.getByTestId("row-grid")).toContainText("Ann")
  await expect(sheets.getByTestId("sheet-People")).toHaveAttribute(
    "aria-selected",
    "true"
  )

  // A sheet knows where it sits, and cannot be renamed, deleted or downloaded.
  await page.getByTestId("grid-structure").click()
  await expect(page.getByTestId("structure-format")).toContainText("budget.xlsx")
  await expect(page.getByTestId("structure-format")).toContainText("2 of 3")

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("plays a sound file and a recording, and draws a PDF", async ({ page }) => {
  const name = `e2e-media-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)

  // A sound file states what its container proved before anything plays.
  await openNode(page, "tone.wav")
  await expect(page.getByTestId("media-details")).toContainText("WAV")
  await expect(page.getByTestId("media-details")).toContainText("8 kHz")
  await expect(page.getByTestId("media-details")).toContainText("0:02")
  const audio = page.getByTestId("media-player")
  await expect(audio).toBeVisible()

  // The element loads through the ranged route, so it knows the length.
  await expect
    .poll(async () => audio.evaluate((element: HTMLMediaElement) => element.duration))
    .toBeCloseTo(2, 1)

  // The two commands beside the details are not drawn the colour of a disabled
  // control. The head painted everything inside it muted to grey that line of
  // text, and a flat button takes its colour from whatever contains it — so
  // both looked dead while working perfectly.
  const mutedText = await page
    .getByTestId("media-details")
    .evaluate((element) => getComputedStyle(element).color)
  const command = await page
    .getByTestId("panel-reveal")
    .evaluate((element) => getComputedStyle(element).color)
  expect(command).not.toBe(mutedText)

  // A recording opens in the same panel with the picture size beside it.
  await openNode(page, "clip.mp4")
  await expect(page.getByTestId("media-details")).toContainText("160 × 120")
  const video = page.getByTestId("media-player")
  await expect(video).toBeVisible()
  await expect
    .poll(async () => video.evaluate((element: HTMLMediaElement) => element.readyState))
    .toBeGreaterThan(0)

  // A PDF is drawn by the application: a canvas per page, and the text over it.
  await openNode(page, "guide.pdf")
  await expect(page.getByTestId("pdf-details")).toContainText("PDF 1.7")
  await expect(page.getByTestId("pdf-details")).toContainText("2 pages")
  const firstPage = page.getByTestId("pdf-page-1")
  await expect(firstPage.locator("canvas")).toBeVisible()
  // The text layer is what makes the page selectable and findable.
  await expect(firstPage.locator(".textLayer")).toContainText("DataPlayer")

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("walks into an archive and reads what is inside it", async ({ page }) => {
  const name = `e2e-archive-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)

  const list = page.getByTestId("catalog-list")
  await expect(list).toContainText("bundle.zip")

  // An archive is a place: it is walked into, and the path says where we are.
  await openNode(page, "bundle.zip")
  await expect(page.getByTestId("catalog-path")).toContainText("bundle.zip")
  await expect(list).toContainText("docs")
  await expect(list).toContainText("readme.md")

  // A document inside it opens in its own viewer, unpacked by nobody.
  await openNode(page, "readme.md")
  await expect(page.getByTestId("markdown-document")).toContainText("Inside an archive")

  // A folder inside the archive is another level of the same catalog.
  await openNode(page, "docs")
  await expect(page.getByTestId("catalog-path")).toContainText("docs")
  await expect(list).toContainText("cities.csv")

  // And a table inside an archive is read like any other table.
  await openNode(page, "cities.csv")
  const grid = page.getByTestId("row-grid")
  await expect(grid).toContainText("name")
  await expect(grid.locator("tbody tr")).toHaveCount(3)

  // What is inside an archive is downloaded on its own, and changed by nothing.
  await catalogCheck(page, "cities.csv").click()
  const started = page.waitForEvent("download")
  await catalogAction(page, "download")
  expect((await started).suggestedFilename()).toBe("cities.csv")

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})


test("packs a selection into an archive and takes it apart again", async ({ page }) => {
  const name = `e2e-packing-${Date.now()}`
  const folder = `packed-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)

  // A folder of this run's own, so the samples every other scenario reads are
  // left where they are.
  await catalogAction(page, "create_folder")
  await page.getByTestId("field-name").fill(folder)
  await page.getByTestId("action-submit").click()
  await openNode(page, folder)

  await catalogAction(page, "upload")
  await page.getByTestId("action-file").setInputFiles([
    { name: "one.txt", mimeType: "text/plain", buffer: Buffer.from("first\n") },
    { name: "two.txt", mimeType: "text/plain", buffer: Buffer.from("second\n") },
  ])
  await page.getByTestId("action-submit").click()
  const list = page.getByTestId("catalog-list")
  await expect(list).toContainText("one.txt")
  await expect(list).toContainText("two.txt")

  // Both ticked: one archive out of a selection, in one request (D68).
  await catalogCheck(page, "one.txt").click()
  await catalogCheck(page, "two.txt").click()
  await catalogAction(page, "create_archive")
  await page.getByTestId("field-name").fill("bundle")
  // The format is a choice the source published; the form knows nothing else.
  await page.getByTestId("field-format").click()
  await page.getByRole("option", { name: "tar.gz", exact: true }).click()
  await page.getByTestId("action-submit").click()
  await expect(catalogRow(page, "bundle.tar.gz")).toBeVisible()

  // Extract is offered for the archive and for neither of the files in it.
  await catalogCheck(page, "one.txt").click()
  await page.getByTestId("catalog-actions").click()
  await expect(page.getByTestId("menu-item-extract_archive")).toHaveAttribute(
    "aria-disabled",
    "true"
  )
  await page.keyboard.press("Escape")
  await catalogCheck(page, "one.txt").click()

  await catalogCheck(page, "bundle.tar.gz").click()
  await catalogAction(page, "extract_archive")
  await page.getByTestId("action-submit").click()
  await expect(catalogRow(page, "bundle")).toBeVisible()

  // What came out is what went in.
  await openNode(page, "bundle")
  await expect(list).toContainText("one.txt")
  await expect(list).toContainText("two.txt")

  // The storage is one person's and outlives the connector, so the scenario
  // takes its own folder away rather than leaving one per run behind.
  await page.getByTestId("catalog-home").click()
  await catalogCheck(page, folder).click()
  await catalogAction(page, "delete")
  await page.getByTestId("action-submit").click()
  await expect(catalogRow(page, folder)).toHaveCount(0)

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})


test("copies a file into another folder, then moves one out again", async ({ page }) => {
  const name = `e2e-paste-${Date.now()}`
  const folder = `pasted-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)

  await catalogAction(page, "create_folder")
  await page.getByTestId("field-name").fill(folder)
  await page.getByTestId("action-submit").click()
  await expect(catalogRow(page, folder)).toBeVisible()

  // Copy changes nothing on its own: it remembers what is ticked (D74). It is
  // a line of the one menu, beside the source's own actions.
  await catalogCheck(page, "notes.txt").click()
  await catalogAction(page, "client:copy")
  await catalogCheck(page, "notes.txt").click()

  // Paste acts on the place being looked at, so the folder is walked into. It
  // asks nothing — what to put here and whether it was cut are both already
  // known — so it runs from the menu without a window in between.
  await openNode(page, folder)
  await catalogAction(page, "paste")
  const list = page.getByTestId("catalog-list")
  await expect(list).toContainText("notes.txt")
  await expect(page.getByTestId("action-dialog")).toHaveCount(0)

  // And what was copied stays where it was.
  await page.getByTestId("catalog-home").click()
  await expect(catalogRow(page, "notes.txt")).toBeVisible()

  // Cut takes it away from where it was.
  await openNode(page, folder)
  await catalogCheck(page, "notes.txt").click()
  await catalogAction(page, "client:cut")
  await page.getByTestId("catalog-home").click()
  await catalogAction(page, "paste")
  // Refused, and the window comes up for it: the name is taken at the top,
  // because the copy from a moment ago is still there.
  await expect(page.getByTestId("action-error")).toContainText("already there")
  await page.getByRole("button", { name: "Cancel" }).click()

  // Leave the storage as it was found.
  await catalogCheck(page, folder).click()
  await catalogAction(page, "delete")
  await page.getByTestId("action-submit").click()
  await expect(catalogRow(page, folder)).toHaveCount(0)

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("says what a node is, whatever it can be opened as", async ({ page }) => {
  const name = `e2e-details-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)

  // A text file: the facts every node has, and what its format states (D75).
  await catalogCheck(page, "notes.txt").click()
  await catalogAction(page, "client:details")
  const details = page.getByTestId("summary-view")
  await expect(details).toContainText("notes.txt")
  await expect(details).toContainText("File")
  await expect(details).toContainText("Lines")
  await expect(details).toContainText("UTF-8")
  // The source's own wording for the view, not this screen's.
  await expect(details).toContainText("View as text")
  await catalogCheck(page, "notes.txt").click()

  // A folder is described too, and is not asked what it opens as.
  await catalogCheck(page, "reports").click()
  await catalogAction(page, "client:details")
  await expect(details).toContainText("Folder")
  await expect(details).toContainText("Files")
  await expect(details).not.toContainText("Opens as")
  await catalogCheck(page, "reports").click()

  // One node at a time: two ticks leave the line there and inert, because a
  // summary is about a node rather than about a selection.
  await catalogCheck(page, "notes.txt").click()
  await catalogCheck(page, "sample.csv").click()
  await page.getByTestId("catalog-actions").click()
  await expect(page.getByTestId("menu-item-client:details")).toHaveAttribute(
    "aria-disabled",
    "true"
  )
  await page.keyboard.press("Escape")
  await expect(page.getByTestId("menu-item-client:details")).toHaveCount(0)

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("finds a file by name anywhere below a folder", async ({ page }) => {
  const name = `e2e-search-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)

  const list = page.getByTestId("catalog-list")
  // Quasar forwards data-testid on a field to the <input> itself.
  const filter = page.getByTestId("catalog-filter")

  // The same words filter this level, as they always did.
  await filter.fill("q3")
  await expect(list).not.toContainText("notes.txt")
  await expect(list).toContainText("Nothing here")

  // And the button beside them looks everywhere below (D76): q3.csv lives in
  // reports, one level down, so only a search can find it from here.
  await page.getByTestId("catalog-search").click()
  await expect(page.getByTestId("catalog-search-summary")).toContainText("q3")
  await expect(list).toContainText("q3.csv")
  // A result says where it was found, because a name alone does not.
  await expect(list).toContainText("reports")

  // A found file opens like any other row, and the results stay.
  await page.getByTestId("catalog-node-q3.csv").click()
  await expect(page.getByTestId("row-grid")).toContainText("quarter")
  await expect(page.getByTestId("catalog-search-summary")).toBeVisible()

  // Closing the search puts the level back, with the words still filtering it.
  await page.getByTestId("catalog-search-close").click()
  await expect(page.getByTestId("catalog-search-summary")).toHaveCount(0)
  await expect(filter).toHaveValue("q3")

  // History restores the text as a filter without starting another recursive search.
  await filter.fill("")
  await filter.click()
  await page.getByTestId("menu-item-q3").click()
  await expect(filter).toHaveValue("q3")
  await expect(page.getByTestId("catalog-search-summary")).toHaveCount(0)
  await expect(list).toContainText("Nothing here")

  // A folder that was found is walked into, and walking ends the search.
  await filter.fill("reports")
  await page.getByTestId("catalog-search").click()
  await page.getByTestId("catalog-node-reports").click()
  await expect(page.getByTestId("catalog-path")).toContainText("reports")
  await expect(page.getByTestId("catalog-search-summary")).toHaveCount(0)

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})
