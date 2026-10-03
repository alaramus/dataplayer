import { expect } from "@playwright/test"
import type { Locator, Page } from "@playwright/test"

/**
 * The search in the header and the Search tab (D205).
 *
 * The field is a combobox over a listbox; the tab is a workspace panel. Both
 * are reached the way a reader reaches them: by role and name.
 */
export function searchField(page: Page): Locator {
  return page.getByRole("combobox", { name: "Search everything" })
}

export function searchList(page: Page): Locator {
  return page.getByRole("listbox", { name: "Search everything" })
}

/** Open the search with its shortcut, as Windows and Linux spell it. */
export async function openSearch(page: Page) {
  // The key is heard once the workspace is up, which its button says.
  await expect(page.getByTestId("search-button")).toBeVisible()
  await page.keyboard.press("Control+k")
  await expect(searchField(page)).toBeFocused()
}

/** A row of the list, by what it says. */
export function searchOption(page: Page, name: string | RegExp): Locator {
  return searchList(page).getByRole("option", { name })
}

export function searchTab(page: Page): Locator {
  return page.getByTestId("search-tab")
}

/** A line of an answer, as the server writes it, and how long after the last one it comes. */
export interface ScriptedLine {
  after: number
  line: unknown
}

/**
 * Answer the search from a script instead of the server, line by line and
 * with the pauses given, as a stream: the screen is then shown exactly what a
 * slow or a failed place sends, which no development server can be made to
 * do on demand. What was asked is kept in `window.__searchAsked`.
 *
 * Installed before the page loads, and only for `POST …/api/v1/search`.
 */
export async function scriptSearch(page: Page, lines: ScriptedLine[]) {
  await page.addInitScript((script: ScriptedLine[]) => {
    const original = window.fetch.bind(window)
    const asked: unknown[] = []
    Object.assign(window, { __searchAsked: asked })
    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url
      if (!url.endsWith("/api/v1/search") || init?.method !== "POST") return original(input, init)
      const request: unknown = JSON.parse(String(init.body))
      asked.push(request)
      const signal = init.signal
      const encoder = new TextEncoder()
      const body = new ReadableStream<Uint8Array>({
        async start(controller) {
          for (const step of script) {
            await new Promise((resolve) => setTimeout(resolve, step.after))
            if (signal?.aborted) {
              controller.error(new DOMException("Aborted", "AbortError"))
              return
            }
            controller.enqueue(encoder.encode(`${JSON.stringify(step.line)}\n`))
          }
          controller.close()
        },
      })
      return new Response(body, { status: 200, headers: { "Content-Type": "application/jsonl" } })
    }
  }, lines)
}

/** What the page asked the scripted search, in order. */
export async function searchesAsked(page: Page): Promise<Record<string, unknown>[]> {
  return page.evaluate(
    () => (window as unknown as { __searchAsked?: Record<string, unknown>[] }).__searchAsked ?? []
  )
}

/**
 * Answer every search the page asks with these lines, at once, through the
 * network rather than a script: for a scenario about what a hit opens, where
 * nothing about the timing of the answer matters and the ids it names are
 * made by the scenario after the page has loaded.
 */
export async function answerSearch(page: Page, lines: unknown[]) {
  const body = lines.map((line) => `${JSON.stringify(line)}\n`).join("")
  await page.route(/\/api\/v1\/search$/, (route) =>
    route.request().method() === "POST"
      ? route.fulfill({ status: 200, contentType: "application/jsonl", body })
      : route.fallback()
  )
}

/** The API as the page is signed in to it, for a scenario to make what it needs. */
export async function signedApi(page: Page): Promise<{ base: string; headers: Record<string, string> }> {
  const token = await page.evaluate(() => Object.entries(localStorage)
    .find(([key]) => key.endsWith("access_token"))?.[1])
  expect(token).toBeTruthy()
  const server = await page.evaluate(() => JSON.parse(
    sessionStorage.getItem("dataplayer:active-server:v1") ?? "null"
  ) as { url: string })
  return { base: `${server.url}/api/v1`, headers: { Authorization: `Bearer ${token ?? ""}` } }
}
