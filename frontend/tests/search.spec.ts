import { expect, test } from "@playwright/test"
import type { Locator, Page } from "@playwright/test"

import { openNode } from "./utils/catalog"
import { createFileConnector, createRedisConnector, createSshConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { REDIS, redisCommands } from "./utils/redis"
import {
  answerSearch,
  openSearch,
  scriptSearch,
  searchesAsked,
  searchField,
  searchList,
  searchOption,
  searchTab,
  signedApi,
} from "./utils/search"
import type { ScriptedLine } from "./utils/search"
import { requireE2EService } from "./utils/services"
import { connectorRow, deleteConnector, openConnector } from "./utils/workspace"

test.describe.configure({ timeout: 60_000 })

// The search on screen (D205, S2) and the Search tab (S3). Against the
// running backend where its providers can answer — connection rows, the
// guide, source types — and against a scripted stream where the scenario is
// about a place that is slow, failed or was not asked, which no development
// server does on demand.

function searchButton(page: Page): Locator {
  return page.getByTestId("search-button")
}

function overlay(page: Page): Locator {
  return page.getByTestId("search-field")
}

/** A file connection named for this run, its window put away. */
async function fileConnection(page: Page, prefix: string): Promise<string> {
  const name = `${prefix}-${Date.now()}`
  await createFileConnector(page, name)
  await closeConnectionWindows(page)
  return name
}

/**
 * Close every connection window. A saved draft is renamed into its
 * connection's window while this runs, and its cross is drawn again, so a
 * press that lands on the old one is simply tried again.
 */
async function closeConnectionWindows(page: Page) {
  const closes = page.locator('[data-testid^="window-close-connector"]')
  for (let attempt = 0; attempt < 10 && (await closes.count()) > 0; attempt += 1) {
    await closes.first().click({ timeout: 2000 }).catch(() => undefined)
  }
  await expect(closes).toHaveCount(0)
}

function boxesOverlap(
  a: { x: number; y: number; width: number; height: number },
  b: { x: number; y: number; width: number; height: number }
): boolean {
  return a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height
}

test("Mod+K opens the search from inside the SQL editor and over a maximized window", async ({ page }) => {
  await login(page)
  const name = await fileConnection(page, "e2e-search-keys")

  // The scene lists the key, read off the registry.
  await expect(page.getByTestId("scene-keys")).toContainText("Ctrl K")
  await expect(page.getByTestId("scene-keys")).toContainText("Search everything")

  // From the SQL editor: the browser's own Ctrl+K is not taken, nor CodeMirror's.
  await openConnector(page, name)
  await page.getByTestId("command-queries").click()
  await page.getByTestId("new-query").click()
  await page.locator(".cm-content").click()
  await page.keyboard.type("select 1")
  await openSearch(page)
  await expect(overlay(page)).toBeVisible()
  await expect(page.locator(".cm-content")).toContainText("select 1")

  // The first Escape closes the list and keeps the words; the second gives
  // the focus back to the editor it came from.
  await searchField(page).fill("select")
  await expect(searchList(page)).toBeVisible()
  await page.keyboard.press("Escape")
  await expect(searchList(page)).toHaveCount(0)
  await expect(searchField(page)).toHaveValue("select")
  await page.keyboard.press("Escape")
  await expect(overlay(page)).toHaveCount(0)
  await expect(page.locator(".cm-content")).toBeFocused()
  await expect(page.locator(".cm-content")).toHaveText("select 1")

  // Over a maximized window, which covers the header and its button.
  await page.getByTestId(`connector-edit-${name}`).click()
  const frame = page.locator('[data-testid^="window-connector"]').filter({ has: page.locator("footer") }).first()
  await frame.getByRole("button", { name: "Maximize", exact: true }).click()
  await openSearch(page)
  const field = await overlay(page).boundingBox()
  const window = await frame.boundingBox()
  expect(field).not.toBeNull()
  expect(window).not.toBeNull()
  expect(boxesOverlap(field!, window!)).toBe(true)
  // What is drawn at the field's centre is the field, not the window under it.
  const atCentre = await page.evaluate(
    ([x, y]) => document.elementFromPoint(x!, y!)?.closest('[data-testid="search-field"]') !== null,
    [field!.x + field!.width / 2, field!.y + field!.height / 2]
  )
  expect(atCentre).toBe(true)
  // The words of last time are back, asked again, the list over the window.
  await expect(searchField(page)).toHaveValue("select")
  await expect(searchList(page)).toBeVisible()
  await page.keyboard.press("Escape")
  await page.keyboard.press("Escape")
  await expect(overlay(page)).toHaveCount(0)
  await closeConnectionWindows(page)

  await deleteConnector(page, name)
})

test("on a Mac the search is ⌘K, and Ctrl+K in the SQL editor deletes to the end of the line", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "platform", { get: () => "MacIntel" })
  })
  await login(page)
  const name = await fileConnection(page, "e2e-search-mac")
  await openConnector(page, name)
  await page.getByTestId("command-queries").click()
  await page.getByTestId("new-query").click()
  await page.locator(".cm-content").click()
  await page.keyboard.type("select 1 as kept")
  for (let step = 0; step < " as kept".length; step += 1) await page.keyboard.press("ArrowLeft")
  await page.keyboard.press("Control+k")
  await expect(page.locator(".cm-content")).toHaveText("select 1")
  await expect(overlay(page)).toHaveCount(0)

  await expect(searchButton(page)).toContainText("⌘K")
  await page.keyboard.press("Meta+k")
  await expect(searchField(page)).toBeFocused()
  await page.keyboard.press("Escape")
  await expect(overlay(page)).toHaveCount(0)

  await deleteConnector(page, name)
})

test("Ctrl+K in a terminal reaches the shell", async ({ page }) => {
  await requireE2EService("ssh")
  const name = `e2e-search-terminal-${Date.now()}`
  await login(page)
  await createSshConnector(page, name)
  await closeConnectionWindows(page)
  await openConnector(page, name)
  await page.getByTestId("command-terminals").click()
  const screen = page.getByTestId("terminal-screen")
  await screen.click()
  // Readline's kill-line: everything after the cursor goes, so the shell
  // prints the first word only.
  await page.keyboard.type('echo "dp-$((6*7))" tail-that-goes')
  for (let step = 0; step < " tail-that-goes".length; step += 1) await page.keyboard.press("ArrowLeft")
  await page.keyboard.press("Control+k")
  await page.keyboard.press("Enter")
  await expect(screen).toContainText("dp-42")
  await expect(screen).not.toContainText("dp-42 tail-that-goes")
  await expect(overlay(page)).toHaveCount(0)

  await page.locator('[data-testid^="terminal-close-"]').click()
  await deleteConnector(page, name)
})

test("the list is a combobox a reader can walk, and Enter opens the row walked to", async ({ page }) => {
  await login(page)
  const name = await fileConnection(page, "e2e-search-walk")

  await searchButton(page).click()
  const field = searchField(page)
  await expect(field).toBeFocused()
  await field.fill(name)
  await expect(field).toHaveAttribute("aria-expanded", "true")
  await expect(searchOption(page, new RegExp(name))).toBeVisible()
  // Nothing is active until an arrow is pressed.
  expect(await field.getAttribute("aria-activedescendant")).toBeNull()
  // A polite region says what was searched, and it is not inside the list.
  await expect(page.getByTestId("search-field").getByRole("status")).toHaveCount(1)
  // The last row asks for everything.
  await expect(searchList(page).getByRole("option").last()).toHaveText(/Show all results/)

  await page.keyboard.press("ArrowDown")
  const active = await field.getAttribute("aria-activedescendant")
  expect(active).not.toBeNull()
  const row = page.locator(`[id="${active}"]`)
  await expect(row).toHaveAttribute("role", "option")
  await expect(row).toHaveAttribute("aria-selected", "true")
  await expect(row).toContainText(name)
  await page.keyboard.press("Enter")
  await expect(overlay(page)).toHaveCount(0)
  await expect(page.locator(`[data-testid^="workspace-tab-catalog:"]`, { hasText: name })).toBeVisible()

  await deleteConnector(page, name)
})

test("a connection found from the Dashboards space opens floating over it", async ({ page }) => {
  await login(page)
  const name = await fileConnection(page, "e2e-search-float")
  await page.getByTestId("space-dashboards").click()

  await openSearch(page)
  await searchField(page).fill(name)
  await searchOption(page, new RegExp(name)).click()
  // Still on Dashboards, the catalog in a window over it.
  await expect(page.getByTestId("space-dashboards")).toHaveAttribute("aria-pressed", "true")
  const floating = page.locator('[data-testid^="window-workspace-panel"], [data-testid^="window-"]', { hasText: name })
  await expect(floating.first()).toBeVisible()

  await page.getByTestId("space-data").click()
  await deleteConnector(page, name)
})

test("a connection outside the browser's first page of a hundred opens", async ({ page }) => {
  await login(page)
  const name = await fileConnection(page, "e2e-search-page")
  // The list the browser holds no longer names it, as for the 101st.
  await page.route(/\/api\/v1\/connectors\/(\?.*)?$/, async (route) => {
    if (route.request().method() !== "GET") return route.fallback()
    try {
      const response = await route.fetch()
      const body = (await response.json()) as { data: { name: string }[]; count: number }
      await route.fulfill({
        response,
        json: { ...body, data: body.data.filter((row) => row.name !== name), count: body.count - 1 },
      })
    } catch {
      // The page went on without this answer: a reload aborted it.
    }
  })
  await page.reload()
  await expect(connectorRow(page, name)).toHaveCount(0)

  const read = page.waitForRequest((request) => /\/api\/v1\/connectors\/[0-9a-f-]{36}$/.test(request.url()))
  await openSearch(page)
  await searchField(page).fill(name)
  await searchOption(page, new RegExp(name)).click()
  await read
  await expect(page.locator(`[data-testid^="workspace-tab-catalog:"]`, { hasText: name })).toBeVisible()

  await page.unroute(/\/api\/v1\/connectors\/(\?.*)?$/)
  await page.reload()
  await deleteConnector(page, name)
})

test("with a pair waiting on a long name, the search beside it is never drawn over", async ({ page }) => {
  await login(page)
  const name = `e2e-search-pair-${Date.now()}-`.padEnd(60, "x")
  await createFileConnector(page, name)
  await closeConnectionWindows(page)
  await openConnector(page, name)
  await page.locator('[data-testid="catalog-pair"]:visible').click()
  const waiting = page.getByTestId("pair-waiting")
  await expect(waiting).toBeVisible()

  for (const width of [900, 1024]) {
    await page.setViewportSize({ width, height: 800 })
    await expect.poll(async () => {
      const pair = await waiting.boundingBox()
      const search = await searchButton(page).boundingBox()
      const menu = await page.getByTestId("fullscreen-toggle").boundingBox()
      if (pair === null || search === null || menu === null) return "missing"
      if (boxesOverlap(pair, search)) return "pair over search"
      if (boxesOverlap(search, menu)) return "search over the toggle"
      return "apart"
    }).toBe("apart")
  }

  await page.setViewportSize({ width: 1280, height: 800 })
  await page.getByTestId("pair-waiting-cancel").click()
  await deleteConnector(page, name)
})

const THEMES = ["light", "paper-light", "dark", "paper", "midnight", "dark-blue", "dark-purple"]

test("the header keeps the search on its one row at 1280 and 768 px in every theme", async ({ page }) => {
  await login(page)
  for (const theme of THEMES) {
    await page.evaluate((value) => localStorage.setItem("dataplayer-theme", value), theme)
    await page.reload()
    for (const width of [1280, 768]) {
      await page.setViewportSize({ width, height: 800 })
      const header = page.getByTestId("app-header")
      const button = searchButton(page)
      await expect(button).toBeVisible()
      await expect.poll(async () => {
        const head = await header.boundingBox()
        const search = await button.boundingBox()
        const first = await page.getByTestId("app-toggle-first-panel").boundingBox()
        const toggle = await page.getByTestId("fullscreen-toggle").boundingBox()
        const menu = await page.getByTestId("user-menu").boundingBox()
        if (!head || !search || !first || !toggle || !menu) return "missing"
        if (Math.round(head.height) !== 42) return `header ${head.height}`
        if (search.y < head.y || search.y + search.height > head.y + head.height) return "outside the row"
        for (const [label, other] of [["first", first], ["toggle", toggle], ["menu", menu]] as const) {
          if (boxesOverlap(search, other)) return `over ${label}`
        }
        return "fits"
      }, `${theme} at ${width}`).toBe("fits")
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width)
      // Drawn in the theme's own colours: the field's ground and its words.
      const look = await button.evaluate((element) => {
        const probe = document.createElement("div")
        probe.style.background = "var(--dp-field-surface)"
        probe.style.color = "var(--dp-text-muted)"
        document.body.append(probe)
        const expected = getComputedStyle(probe)
        const result = {
          ground: getComputedStyle(element).backgroundColor === expected.backgroundColor,
          words: getComputedStyle(element).color === expected.color,
        }
        probe.remove()
        return result
      })
      expect(look, `${theme} at ${width}`).toEqual({ ground: true, words: true })
    }
  }
  await page.evaluate(() => localStorage.setItem("dataplayer-theme", "light"))
})

// --- the Search tab ----------------------------------------------------------

const UUID = "00000000-0000-4000-8000-000000000001"

function group(key: string, title: string, rank: number) {
  return { key, title, rank }
}

function planned(key: string, groupOf: ReturnType<typeof group>, place: Record<string, unknown>, connectorId: string | null = null) {
  return { key, cell: { place, field: "names" }, group: groupOf, cost: "instant", way: "live", connector_id: connectorId }
}

function outcome(over: Record<string, unknown> = {}) {
  return {
    way: "live", status: "complete", reason: null, notice: null, error_kind: null, message: null,
    more: false, as_of: null, deadline_seconds: null, since: null, owned: false, ...over,
  }
}

function guideHit(key: string, title: string) {
  return {
    key: `object:guide_page:${key}`,
    target: { kind: "object", object_type: "guide_page", object_id: key },
    title,
    detail: "Guide",
    facts: { kind: "guide_page", changed_at: null, owner: null, switched_off: false },
    match: { field: "name", match_class: "substring", line: null, excerpt: [{ text: title, hit: true }] },
    access: null,
    open: "guide_page",
    via: "live",
    as_of: null,
  }
}

const GUIDE = group("objects:guide", "Guide", 100600)
const TYPES = group("objects:source_types", "Source types", 100700)
const IN_SLOW = group(`connection:${UUID}`, "slow server", 1000)
const GUIDE_CELL = planned("objects:guide/names", GUIDE, { kind: "objects", provider: "guide" })
const TYPES_CELL = planned("objects:source_types/names", TYPES, { kind: "objects", provider: "source_types" })
const SLOW_CELL = planned(`connection:${UUID}/names`, IN_SLOW, { kind: "connection", connector_id: UUID, node_id: null }, UUID)

async function searchInTab(page: Page, words: string) {
  await openSearch(page)
  await searchField(page).fill(words)
  await page.keyboard.press("Enter")
  await expect(searchTab(page)).toBeVisible()
}

test("a slow place fills its own group after the others, moving nothing already drawn", async ({ page }) => {
  const lines: ScriptedLine[] = [
    { after: 0, line: { type: "plan", mode: "search", cells: [SLOW_CELL, GUIDE_CELL, TYPES_CELL] } },
    { after: 50, line: { type: "cell", key: GUIDE_CELL.key, outcome: outcome(), hits: [guideHit("a", "Alpha page"), guideHit("b", "Beta page")] } },
    { after: 50, line: { type: "cell", key: TYPES_CELL.key, outcome: outcome(), hits: [] } },
    { after: 50, line: { type: "best", hits: [] } },
    { after: 2500, line: { type: "cell", key: SLOW_CELL.key, outcome: outcome(), hits: [{
      ...guideHit("slow", "Slow table"),
      key: `node:${UUID}:public.slow:`,
      target: { kind: "node", connector_id: UUID, node_id: "public.slow", parent_id: "public", location: "public", name: "slow", node_kind: "table", sub_key: null, ancestors: null, node: null },
      facts: { kind: "table", changed_at: null, owner: null, switched_off: false },
      open: "rows",
    }] } },
    { after: 0, line: { type: "end", nothing_found: false, asked: 3, superseded: false } },
  ]
  await scriptSearch(page, lines)
  await login(page)
  await searchInTab(page, "page")

  const tab = searchTab(page)
  const slow = tab.getByTestId(`search-group-connection:${UUID}`)
  const hits = tab.getByTestId("search-hit")
  await expect(hits).toHaveText([/Alpha page/, /Beta page/])
  // The slow place has its place already, and says it is being asked.
  await expect(slow).toContainText("Searching…")
  const drawn = await hits.evaluateAll((rows) => {
    const marked = rows.map((row, index) => {
      row.setAttribute("data-drawn", String(index))
      return row.textContent
    })
    return marked
  })

  await expect(slow).toContainText("Slow table")
  await expect(slow).not.toContainText("Searching…")
  // Its hits are in its own group, above the guide as the plan ranks it, and
  // the rows drawn before are the same rows, in the same order.
  await expect(hits).toHaveText([/Slow table/, /Alpha page/, /Beta page/])
  const after = await tab.locator("[data-drawn]").evaluateAll((rows) => rows.map((row) => row.textContent))
  expect(after).toEqual(drawn)
})

test("every place not searched says why, with its gesture, and a gesture asks that place alone", async ({ page }) => {
  const off = planned("connection:off/names", group("connection:off", "switched off one", 1001), { kind: "connection", connector_id: UUID, node_id: null }, UUID)
  const cannot = planned("connection:cannot/names", group("connection:cannot", "cannot one", 1002), { kind: "connection", connector_id: UUID, node_id: null }, UUID)
  const down = planned("connection:down/names", group("connection:down", "down one", 1003), { kind: "connection", connector_id: UUID, node_id: null }, UUID)
  const left = planned("connection:left/names", group("connection:left", "left out", 1004), { kind: "connection", connector_id: UUID, node_id: null }, UUID)
  const late = planned("connection:late/names", group("connection:late", "late one", 1005), { kind: "connection", connector_id: UUID, node_id: null }, UUID)
  const stopped = planned("connection:stopped/names", group("connection:stopped", "stopped one", 1006), { kind: "connection", connector_id: UUID, node_id: null }, UUID)
  const locked = planned("connection:locked/names", group("connection:locked", "locked one", 1007), { kind: "connection", connector_id: UUID, node_id: null }, UUID)
  const lines: ScriptedLine[] = [
    { after: 0, line: { type: "plan", mode: "search", cells: [off, cannot, down, left, late, stopped, locked, GUIDE_CELL] } },
    { after: 0, line: { type: "cell", key: off.key, outcome: outcome({ status: "skipped", reason: "switched_off", way: "none" }), hits: [] } },
    { after: 0, line: { type: "cell", key: cannot.key, outcome: outcome({ status: "skipped", reason: "cannot_search", way: "none" }), hits: [] } },
    { after: 0, line: { type: "cell", key: down.key, outcome: outcome({ status: "skipped", reason: "unreachable", way: "none", since: "2026-10-02T14:02:00" }), hits: [] } },
    { after: 0, line: { type: "cell", key: left.key, outcome: outcome({ status: "skipped", reason: "not_asked", way: "none" }), hits: [] } },
    { after: 0, line: { type: "cell", key: late.key, outcome: outcome({ status: "late", deadline_seconds: 2 }), hits: [] } },
    { after: 0, line: { type: "cell", key: stopped.key, outcome: outcome({ status: "stopped", notice: "Stopped after 100 matches", more: true }), hits: [] } },
    { after: 0, line: { type: "cell", key: locked.key, outcome: outcome({ status: "failed", error_kind: "locked", message: "Locked" }), hits: [] } },
    { after: 0, line: { type: "cell", key: GUIDE_CELL.key, outcome: outcome(), hits: [] } },
    { after: 0, line: { type: "best", hits: [] } },
    { after: 0, line: { type: "end", nothing_found: false, asked: 4, superseded: false } },
  ]
  await scriptSearch(page, lines)
  await login(page)
  await searchInTab(page, "orders")

  const tab = searchTab(page)
  const said = (key: string) => tab.getByTestId(`search-group-${key}`).getByTestId("search-outcome")
  await expect(said("connection:off")).toHaveText("Switched off")
  await expect(said("connection:cannot")).toHaveText("Can't be searched by name")
  await expect(said("connection:down")).toHaveText("Can't be reached since 14:02Search anyway")
  await expect(said("connection:left")).toHaveText("Not searchedSearch these too")
  await expect(said("connection:late")).toHaveText("Didn't answer in 2 sTry again")
  await expect(said("connection:stopped")).toHaveText("Stopped after 100 matchesSearch only this connection")
  await expect(said("connection:locked")).toHaveText("Locked by its owner")
  // Nothing was found, but not everywhere was looked at: no "Nothing found".
  await expect(tab.getByTestId("search-nothing")).toHaveCount(0)

  // Try again asks that place alone, on a lane of its own, beside the answer.
  await said("connection:late").getByRole("button", { name: "Try again" }).click()
  await expect.poll(async () => (await searchesAsked(page)).length).toBe(2)
  const follow = (await searchesAsked(page))[1]
  expect(follow).toMatchObject({ words: "orders", mode: "search", lane: "follow", only: [late.cell.place], insist: true })
  await said("connection:down").getByRole("button", { name: "Search anyway" }).click()
  await expect.poll(async () => (await searchesAsked(page)).length).toBe(3)
  expect((await searchesAsked(page))[2]).toMatchObject({ lane: "follow", only: [down.cell.place], insist: true })
})

test("Nothing found is said only when every place asked looked everywhere", async ({ page }) => {
  const lines: ScriptedLine[] = [
    { after: 0, line: { type: "plan", mode: "search", cells: [GUIDE_CELL, TYPES_CELL] } },
    { after: 0, line: { type: "cell", key: GUIDE_CELL.key, outcome: outcome(), hits: [] } },
    { after: 0, line: { type: "cell", key: TYPES_CELL.key, outcome: outcome(), hits: [] } },
    { after: 0, line: { type: "best", hits: [] } },
    { after: 0, line: { type: "end", nothing_found: true, asked: 2, superseded: false } },
  ]
  await scriptSearch(page, lines)
  await login(page)
  await searchInTab(page, "zzqq")
  await expect(searchTab(page).getByTestId("search-nothing")).toContainText("Nothing found in all 2 places")
})

test("the Search tab opens from Enter, stays in sight as its hits open, and comes back empty", async ({ page }) => {
  await login(page)
  const name = await fileConnection(page, "e2e-search-tab")

  await searchInTab(page, name)
  const tab = searchTab(page)
  await expect(page.getByTestId("search-tab-words")).toHaveValue(name)
  const hit = tab.getByTestId("search-hit").filter({ hasText: name })
  await expect(hit).toBeVisible()
  await expect(tab.getByTestId("search-filter-group")).toBeVisible()
  await hit.click()
  await expect(page.locator(`[data-testid^="workspace-tab-catalog:"]`, { hasText: name })).toBeVisible()
  await expect(tab).toBeVisible()

  // The words were kept for this browser tab, and the empty field offers them.
  await openSearch(page)
  await searchField(page).fill("")
  await expect(searchList(page).getByRole("group", { name: "Recent searches" })).toContainText(name)
  await page.keyboard.press("Escape")
  await page.keyboard.press("Escape")

  // Restored from the layout, the tab holds no words.
  await page.reload()
  await expect(searchTab(page)).toBeVisible()
  await expect(page.getByTestId("search-tab-words")).toHaveValue("")
  await expect(searchTab(page).getByTestId("search-hit")).toHaveCount(0)

  await page.getByRole("button", { name: "Close Search", exact: true }).click()
  await deleteConnector(page, name)
})

test("Enter while Dashboards is shown opens the Search tab in a window over it", async ({ page }) => {
  await login(page)
  await page.getByTestId("space-dashboards").click()
  await searchInTab(page, "connections")
  await expect(page.getByTestId("space-dashboards")).toHaveAttribute("aria-pressed", "true")
  await expect(page.locator('[data-testid^="window-"]').filter({ has: searchTab(page) }).first()).toBeVisible()
})

test("a catalog with the focus is offered as the scope, and the scope names it and its level", async ({ page }) => {
  await login(page)
  const name = await fileConnection(page, "e2e-search-scope")
  await openConnector(page, name)
  const catalog = page.locator('[data-testid^="workspace-tab-catalog:"]', { hasText: name })
  await expect(catalog).toBeVisible()
  await page.getByTestId("catalog-filter").click()

  await openSearch(page)
  const offer = searchList(page).getByRole("option").first()
  await expect(offer).toHaveAccessibleName(`Search in ${name}`)
  await searchField(page).fill("reports")
  await page.keyboard.press("ArrowRight")
  await expect(page.getByTestId("combobox-chip")).toHaveText(name)
  // Backspace before the first word takes the scope away, the words kept.
  await page.keyboard.press("Home")
  await page.keyboard.press("Backspace")
  await expect(page.getByTestId("combobox-chip")).toHaveCount(0)
  await expect(searchField(page)).toHaveValue("reports")

  await page.keyboard.press("ArrowDown")
  await expect(searchList(page).getByRole("option").first()).toHaveAttribute("aria-selected", "true")
  const asked = page.waitForRequest(
    (request) => request.url().endsWith("/api/v1/search") && (request.postDataJSON() as { lane?: string }).lane === "tab"
  )
  await page.keyboard.press("Enter")
  await expect(page.getByTestId("combobox-chip")).toHaveText(name)
  await page.keyboard.press("End")
  await page.keyboard.press("Enter")
  const request = (await asked).postDataJSON() as { only: { kind: string; connector_id: string; node_id: string | null }[] }
  expect(request.only).toHaveLength(1)
  expect(request.only[0]?.kind).toBe("connection")
  await expect(page.getByTestId("search-tab-scope")).toContainText(name)

  await page.getByTestId("space-data").click()
  await deleteConnector(page, name)
})

test("a guide page and a source type open where they live", async ({ page }) => {
  await login(page)
  await openSearch(page)
  await searchField(page).fill("TimescaleDB")
  await searchList(page).getByRole("group", { name: "Source types" }).getByRole("option", { name: /PostgreSQL/ }).click()
  await expect(page.getByTestId("connector-name")).toBeVisible()
  await closeConnectionWindows(page)

  await openSearch(page)
  await searchField(page).fill("connections")
  const guide = searchList(page).getByRole("group", { name: "Guide" }).getByRole("option").first()
  await expect(guide).toBeVisible()
  await guide.click()
  await expect(page.locator('[data-testid^="window-guide"]').first()).toBeVisible()
})

test("an SSH key found opens Preferences on it", async ({ page }) => {
  const keys = group("objects:ssh_keys", "SSH keys", 100500)
  const cell = planned("objects:ssh_keys/names", keys, { kind: "objects", provider: "ssh_keys" })
  const found = {
    ...guideHit("deploy", "deploy key"),
    key: "object:ssh_key:k1",
    target: { kind: "object", object_type: "ssh_key", object_id: "k1" },
    detail: "ed25519",
    facts: { kind: "ssh_key", changed_at: null, owner: null, switched_off: false },
    open: "ssh_key",
  }
  await scriptSearch(page, [
    { after: 0, line: { type: "plan", mode: "typing", cells: [cell] } },
    { after: 0, line: { type: "cell", key: cell.key, outcome: outcome(), hits: [found] } },
    { after: 0, line: { type: "best", hits: [] } },
    { after: 0, line: { type: "end", nothing_found: false, asked: 1, superseded: false } },
  ])
  await login(page)
  await openSearch(page)
  await searchField(page).fill("deploy")
  await searchOption(page, /deploy key/).click()
  await expect(page).toHaveURL(/\/preferences\?key=k1$/)
  await expect(page.getByTestId("ssh-keys")).toBeVisible()
  // Preferences has nowhere to open a hit into, so no search either.
  await expect(page.getByTestId("search-button")).toHaveCount(0)
})

// --- what a hit opens, and Show in catalog (S4, S5) ---------------------------
//
// The answer is the network's, made by the scenario: the ids it names are of
// things the scenario makes after the page has loaded, and what is tested is
// where they open, not how they were found.

/** One place's answer, holding these hits, as the field reads it. */
function answerOf(cell: ReturnType<typeof planned>, hits: unknown[]): unknown[] {
  return [
    { type: "plan", mode: "typing", cells: [cell] },
    { type: "cell", key: cell.key, outcome: outcome(), hits },
    { type: "best", hits: [] },
    { type: "end", nothing_found: false, asked: 1, superseded: false },
  ]
}

function objectsCell(provider: string, title: string) {
  return planned(`objects:${provider}/names`, group(`objects:${provider}`, title, 100100), { kind: "objects", provider })
}

function objectHit(type: string, id: string, title: string) {
  return {
    ...guideHit(id, title),
    key: `object:${type}:${id}`,
    target: { kind: "object", object_type: type, object_id: id },
    detail: null,
    facts: { kind: type, changed_at: null, owner: null, switched_off: false },
    open: type,
  }
}

interface FoundNode {
  node: { id: string; name: string; kind: string }
  parent_id: string | null
  location: string
}

/**
 * A node as live finds it, its listing's node in hand; or, for a key, with
 * no listing and the levels above it named instead.
 */
function nodeHit(connectorId: string, found: FoundNode, ancestors: { node_id: string; name: string }[] | null = null) {
  return {
    key: `node:${connectorId}:${found.node.id}:`,
    target: {
      kind: "node",
      connector_id: connectorId,
      node_id: found.node.id,
      parent_id: found.parent_id,
      location: found.location,
      name: found.node.name,
      node_kind: found.node.kind,
      sub_key: null,
      ancestors,
      node: ancestors === null ? found.node : null,
    },
    title: found.node.name,
    detail: found.location,
    facts: { kind: found.node.kind, changed_at: null, owner: null, switched_off: false },
    match: { field: "name", match_class: "exact", line: null, excerpt: [{ text: found.node.name, hit: true }] },
    access: null,
    open: "preferred",
    via: "live",
    as_of: null,
  }
}

function connectionCell(connectorId: string, name: string) {
  return planned(
    `connection:${connectorId}/names`,
    group(`connection:${connectorId}`, name, 1000),
    { kind: "connection", connector_id: connectorId, node_id: null },
    connectorId
  )
}

/** The id of a connection's own catalog, read off its tab. */
async function catalogConnectorId(page: Page, name: string): Promise<string> {
  const tab = page.locator('[data-testid^="workspace-tab-catalog:"]', { hasText: name }).first()
  await expect(tab).toBeVisible()
  const testId = (await tab.getAttribute("data-testid")) ?? ""
  return testId.replace("workspace-tab-catalog:", "")
}

test("a dashboard opens from the field with the Dashboards space already shown once", async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 900 })
  await login(page)
  await page.getByTestId("space-dashboards").click()
  const rail = page.getByTestId("dashboards-rail")
  await expect(rail.or(page.getByTestId("store-setup"))).toBeVisible()
  test.skip(!(await rail.isVisible()), "The metrics store is not set up on this stack")

  // Two dashboards. New gives back an empty one the person already has
  // (D129), so the first is given a widget before the second is asked for.
  const { base, headers } = await signedApi(page)
  const stamp = String(Date.now())
  const agent = await page.request.post(`${base}/metrics/agents`, { headers, data: { name: `e2e-search-agent-${stamp}` } })
  expect(agent.ok(), await agent.text()).toBe(true)
  const agentId = ((await agent.json()) as { agent: { id: string } }).agent.id
  interface Made { id: string; name: string; color: string | null; version: number; options: object }
  const make = async (name: string): Promise<Made> => {
    const made = await page.request.post(`${base}/metrics/dashboards`, { headers, data: { name } })
    expect(made.ok(), await made.text()).toBe(true)
    return (await made.json()) as Made
  }
  const first = await make(`e2e-search-first-${stamp}`)
  const filled = await page.request.put(`${base}/metrics/dashboards/${first.id}`, {
    headers,
    data: {
      name: `e2e-search-first-${stamp}`,
      color: first.color,
      version: first.version,
      options: first.options,
      widgets: [{
        type: "processes",
        id: crypto.randomUUID(),
        title: "Processes",
        layout: { x: 0, y: 0, w: 6, h: 6 },
        agent_id: agentId,
        host: "e2e-host",
      }],
    },
  })
  expect(filled.ok(), await filled.text()).toBe(true)
  const firstName = `e2e-search-first-${stamp}`
  const second = await make(`e2e-search-second-${stamp}`)
  expect(second.id).not.toBe(first.id)

  try {
    // Shown once, with the first dashboard open in it; then Data.
    await page.reload()
    await expect(page.getByTestId("dashboards-space")).toBeVisible()
    await page.getByTestId(`dashboard-${firstName}`).click()
    await expect(page.getByTestId("dashboard-name")).toHaveText(firstName)
    await page.getByTestId("space-data").click()
    await expect(page.getByTestId("dashboards-space")).toBeHidden()

    await answerSearch(page, answerOf(objectsCell("dashboards", "Dashboards"), [objectHit("dashboard", second.id, second.name)]))
    await openSearch(page)
    await searchField(page).fill("e2e-search-second")
    await searchOption(page, new RegExp(second.name)).click()

    await expect(page.getByTestId("space-dashboards")).toHaveAttribute("aria-pressed", "true")
    await expect(page.getByTestId("dashboard-name")).toHaveText(second.name)
  } finally {
    for (const id of [first.id, second.id]) await page.request.delete(`${base}/metrics/dashboards/${id}`, { headers })
    await page.request.delete(`${base}/metrics/agents/${agentId}`, { headers })
    await page.unrouteAll({ behavior: "ignoreErrors" })
  }
})

test("a pipeline opens from the field in its space, over the one last open there", async ({ page }) => {
  await login(page)
  const { base, headers } = await signedApi(page)
  const stamp = String(Date.now())
  const make = async (name: string): Promise<{ id: string; name: string }> => {
    const made = await page.request.post(`${base}/pipelines`, { headers, data: { name } })
    expect(made.ok(), await made.text()).toBe(true)
    return (await made.json()) as { id: string; name: string }
  }
  const first = await make(`e2e-search-pipe-first-${stamp}`)
  const second = await make(`e2e-search-pipe-second-${stamp}`)

  try {
    await page.reload()
    await page.getByTestId("space-pipelines").click()
    await page.getByTestId("pipeline-switcher").click()
    await page.getByRole("option", { name: first.name }).click()
    await expect(page.getByTestId("pipeline-view")).toContainText(first.name)
    await page.getByTestId("space-data").click()

    await answerSearch(page, answerOf(objectsCell("pipelines", "Pipelines"), [objectHit("pipeline", second.id, second.name)]))
    await openSearch(page)
    await searchField(page).fill("e2e-search-pipe-second")
    await searchOption(page, new RegExp(second.name)).click()

    await expect(page.getByTestId("space-pipelines")).toHaveAttribute("aria-pressed", "true")
    await expect(page.getByTestId("pipeline-view")).toContainText(second.name)
  } finally {
    for (const id of [first.id, second.id]) await page.request.delete(`${base}/pipelines/${id}`, { headers })
    await page.unrouteAll({ behavior: "ignoreErrors" })
  }
})

test("a conversation opens from the field before the AI space has ever been shown", async ({ page }) => {
  await login(page)
  await page.getByTestId("space-data").click()
  const { base, headers } = await signedApi(page)
  const made: string[] = []
  for (let index = 0; index < 2; index += 1) {
    const created = await page.request.post(`${base}/ai/conversations`, { headers })
    expect(created.ok(), await created.text()).toBe(true)
    made.push(((await created.json()) as { id: string }).id)
  }
  // The older of the two: the space left to itself would open the newer.
  const wanted = made[0] ?? ""

  try {
    // Loaded on Data, so the AI space has not been drawn on this page at all.
    await page.reload()
    await expect(page.getByTestId("search-button")).toBeVisible()
    await expect(page.getByTestId("ai-space")).toHaveCount(0)

    await answerSearch(page, answerOf(objectsCell("conversations", "Conversations"), [objectHit("conversation", wanted, "e2e search chat")]))
    await openSearch(page)
    await searchField(page).fill("e2e search chat")
    await searchOption(page, /e2e search chat/).click()

    await expect(page.getByTestId("space-ai")).toHaveAttribute("aria-pressed", "true")
    await expect(page.locator('[data-testid^="ai-chat-row-"][data-active="true"]'))
      .toHaveAttribute("data-testid", `ai-chat-row-${wanted}`)
  } finally {
    for (const id of made) await page.request.delete(`${base}/ai/conversations/${id}`, { headers })
    await page.unrouteAll({ behavior: "ignoreErrors" })
  }
})

test("Show in catalog keeps a catalog's contents search on screen", async ({ page }) => {
  await login(page)
  // Read inside files without the warning in front of it: the warning is
  // the catalog's own scenario.
  await page.evaluate(() => localStorage.setItem("dataplayer-content-search-ask", "never"))
  const name = await fileConnection(page, "e2e-search-reveal")
  await openConnector(page, name)
  const connectorId = await catalogConnectorId(page, name)

  // The catalog searches inside its files from the top: q3.csv, a level down,
  // is found by a word in it.
  await page.getByTestId("catalog-filter").fill("quarter")
  await page.getByTestId("catalog-search").click({ modifiers: ["Shift"] })
  const summary = page.getByTestId("catalog-search-summary")
  await expect(summary).toContainText("quarter")
  await expect(page.getByTestId("catalog-list")).toContainText("q3.csv")

  const { base, headers } = await signedApi(page)
  const read = await page.request.get(`${base}/connectors/${connectorId}/catalog/search`, { headers, params: { query: "q3.csv" } })
  expect(read.ok(), await read.text()).toBe(true)
  const found = ((await read.json()) as { matches: FoundNode[] }).matches.find((one) => one.node.name === "q3.csv")
  expect(found).toBeDefined()
  if (found === undefined) return
  await answerSearch(page, answerOf(connectionCell(connectorId, name), [nodeHit(connectorId, found)]))

  await openSearch(page)
  await searchField(page).fill("q3.csv")
  await searchOption(page, /q3\.csv/).getByRole("button", { name: "Show in catalog" }).click()
  await expect(overlay(page)).toHaveCount(0)

  // Not wiped: the search stays where it was, and a second catalog of the
  // connection stands where the file lives, pointing at it.
  await expect(page.getByTestId("catalog-panel")).toHaveCount(2)
  await expect(summary).toHaveCount(1)
  await expect(summary).toContainText("quarter")
  const copy = page.getByTestId("catalog-panel").filter({ has: page.getByTestId("catalog-path").filter({ hasText: "reports" }) })
  await expect(copy.getByTestId("catalog-node-q3.csv")).toHaveAttribute("data-revealed", "true")

  // Asked again, by the keys of the active row: the catalog already standing
  // there points again, and no third one is made.
  await expect(copy.getByTestId("catalog-node-q3.csv")).not.toHaveAttribute("data-revealed", "true", { timeout: 10_000 })
  await openSearch(page)
  const field = searchField(page)
  await field.fill("q3.csv")
  const option = searchOption(page, /q3\.csv/)
  await expect(option).toBeVisible()
  // Past the offer to search in the catalog that has the focus.
  const optionId = (await option.getAttribute("id")) ?? ""
  for (let step = 0; step < 5 && (await field.getAttribute("aria-activedescendant")) !== optionId; step += 1) {
    await page.keyboard.press("ArrowDown")
  }
  await expect(field).toHaveAttribute("aria-activedescendant", optionId)
  await page.keyboard.press("Control+Enter")
  await expect(copy.getByTestId("catalog-node-q3.csv")).toHaveAttribute("data-revealed", "true")
  await expect(page.getByTestId("catalog-panel")).toHaveCount(2)
  await expect(summary).toContainText("quarter")

  // And from the Search tab, where the row offers it as a button of its own,
  // the tab staying in sight.
  await expect(copy.getByTestId("catalog-node-q3.csv")).not.toHaveAttribute("data-revealed", "true", { timeout: 10_000 })
  await openSearch(page)
  await field.fill("q3.csv")
  await page.keyboard.press("Enter")
  const tabHit = searchTab(page).getByTestId("search-hit").filter({ hasText: "q3.csv" })
  await tabHit.getByRole("button", { name: "Show in catalog" }).click()
  await expect(copy.getByTestId("catalog-node-q3.csv")).toHaveAttribute("data-revealed", "true")
  await expect(searchTab(page)).toBeVisible()
  await expect(page.getByTestId("catalog-panel")).toHaveCount(2)
  await expect(summary).toContainText("quarter")
  await page.getByRole("button", { name: "Close Search", exact: true }).click()

  await page.unrouteAll({ behavior: "ignoreErrors" })
  await deleteConnector(page, name)
})

test("an open tab is brought forward, and a saved tab group restored after its warning", async ({ page }) => {
  await login(page)
  const name = await fileConnection(page, "e2e-search-tabs")
  await openConnector(page, name)
  await openNode(page, "notes.txt")
  await openNode(page, "sample.csv")
  const tabs = page.locator('[data-testid^="workspace-tab-"]:not([data-testid^="workspace-tab-icon"])')
  const notes = tabs.filter({ hasText: "notes.txt" })
  const sample = tabs.filter({ hasText: "sample.csv" })
  await expect(sample).toHaveClass(/--active/)
  // A tab is found by its panel, which is what the browser sends it as (S9).
  const panelId = ((await notes.getAttribute("data-testid")) ?? "").replace("workspace-tab-", "")

  await answerSearch(page, answerOf(objectsCell("open_tabs", "Open tabs"), [objectHit("tab", panelId, "notes.txt")]))
  await openSearch(page)
  await searchField(page).fill("notes")
  await searchOption(page, /notes\.txt/).click()
  await expect(notes).toHaveClass(/--active/)

  // A group saved with both tabs, and the warning asked for again.
  const group = `e2e search group ${String(Date.now())}`
  await page.getByTestId("save-tab-group").click()
  await page.getByTestId("tab-group-name").fill(group)
  await page.getByTestId("confirm-tab-group-name").click()
  const groupId = await page.evaluate((wanted) => {
    let id = ""
    for (const [key, value] of Object.entries(localStorage)) {
      if (key.includes("dataplayer-tab-groups:skip-warning:")) {
        localStorage.removeItem(key)
      } else if (key.includes("dataplayer-tab-groups:")) {
        const saved = JSON.parse(value) as { groups: { id: string; name: string }[] }
        id = saved.groups.find((one) => one.name === wanted)?.id ?? id
      }
    }
    return id
  }, group)
  expect(groupId).not.toBe("")
  await sample.locator('[data-testid^="workspace-close-"]').click()
  await expect(sample).toHaveCount(0)

  await page.unrouteAll({ behavior: "ignoreErrors" })
  await answerSearch(page, answerOf(objectsCell("open_tabs", "Open tabs"), [objectHit("tab_group", groupId, group)]))
  await openSearch(page)
  await searchField(page).fill("e2e search group")
  await searchOption(page, new RegExp(group)).click()
  const warning = page.getByRole("dialog", { name: "Replace current tabs?", exact: true })
  await expect(warning).toBeVisible()
  await warning.getByTestId("confirm-accept").click()
  await expect(sample).toHaveCount(1)

  await page.unrouteAll({ behavior: "ignoreErrors" })
  await deleteConnector(page, name)
})

test("a catalog already on the node's level leaves its search results and marks the row", async ({ page }) => {
  await login(page)
  const name = await fileConnection(page, "e2e-search-leave")
  await openConnector(page, name)
  const connectorId = await catalogConnectorId(page, name)
  await openNode(page, "reports")
  const filter = page.getByTestId("catalog-filter")
  await filter.fill("q3")
  await page.getByTestId("catalog-search").click()
  await expect(page.getByTestId("catalog-search-summary")).toContainText("q3")

  const { base, headers } = await signedApi(page)
  const read = await page.request.get(`${base}/connectors/${connectorId}/catalog/search`, { headers, params: { query: "q3.csv" } })
  expect(read.ok(), await read.text()).toBe(true)
  const found = ((await read.json()) as { matches: FoundNode[] }).matches.find((one) => one.node.name === "q3.csv")
  expect(found).toBeDefined()
  if (found === undefined) return
  await answerSearch(page, answerOf(connectionCell(connectorId, name), [nodeHit(connectorId, found)]))

  await openSearch(page)
  await searchField(page).fill("q3.csv")
  await searchOption(page, /q3\.csv/).getByRole("button", { name: "Show in catalog" }).click()

  // The same catalog, back on its level, the words a filter again and the
  // row they leave marked.
  await expect(page.getByTestId("catalog-search-summary")).toHaveCount(0)
  await expect(page.getByTestId("catalog-node-q3.csv")).toHaveAttribute("data-revealed", "true")
  await expect(page.getByTestId("catalog-panel")).toHaveCount(1)
  await expect(filter).toHaveValue("q3")

  await page.unrouteAll({ behavior: "ignoreErrors" })
  await deleteConnector(page, name)
})

test("a Redis key found is shown in its tree, down the folders its hit names", async ({ page }) => {
  await requireE2EService("redis")
  const stamp = String(Date.now())
  const database = REDIS.database
  const key = `s${stamp}:deep:token`
  const name = `e2e-search-redis-${stamp}`
  await redisCommands([["SET", key, "abc"]])
  try {
    await login(page)
    await createRedisConnector(page, name)
    await closeConnectionWindows(page)
    const { base, headers } = await signedApi(page)
    const listed = await page.request.get(`${base}/connectors/`, { headers, params: { limit: 1000 } })
    expect(listed.ok(), await listed.text()).toBe(true)
    const connectorId = ((await listed.json()) as { data: { id: string; name: string }[] }).data
      .find((one) => one.name === name)?.id ?? ""
    expect(connectorId).not.toBe("")

    // A key has no node path (D195): where it lives is what its hit says.
    const found = nodeHit(connectorId, { node: { id: `k${database}:${key}`, name: key, kind: "key" }, parent_id: null, location: `db${database}` }, [
      { node_id: `d${database}`, name: `db${database}` },
      { node_id: `f${database}:s${stamp}:`, name: `s${stamp}:` },
      { node_id: `f${database}:s${stamp}:deep:`, name: "deep:" },
    ])
    await answerSearch(page, answerOf(connectionCell(connectorId, name), [found]))

    await openSearch(page)
    await searchField(page).fill("deep token")
    await searchOption(page, new RegExp(key)).getByRole("button", { name: "Show in catalog" }).click()

    await expect(page.getByTestId(`keyspace-row-f${database}:s${stamp}:deep:`)).toBeVisible()
    await expect(page.getByTestId(`keyspace-row-k${database}:${key}`)).toHaveAttribute("aria-selected", "true")

    await page.unrouteAll({ behavior: "ignoreErrors" })
    await deleteConnector(page, name)
  } finally {
    await redisCommands([["DEL", key]])
  }
})
